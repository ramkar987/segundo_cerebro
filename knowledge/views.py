import uuid

from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import AskLibraryForm, BatchCaptureForm, CaptureForm
from .models import Chunk, Item, ProcessingJob, Relation
from .services.capture import DuplicateCapture, create_capture
from .services.detector import detect_capture
from .services.rag import RagUnavailable, answer_from_library
from .services.semantic import (
    SemanticSearchUnavailable,
    semantic_item_results,
)


def _is_retryable_processing_error(error: str) -> bool:
    text = (error or '').casefold()

    # Rate limit, timeouts e indisponibilidade temporária devem ser repetidos.
    if any(token in text for token in (
        '429',
        'rate limit',
        'too many requests',
        'timed out',
        'timeout',
        '500',
        '502',
        '503',
        '504',
        'json_validate_failed',
        'failed to generate json',
        'failed to validate json',
    )):
        return True

    # Estes erros do Instagram normalmente dependem de autenticação,
    # disponibilidade do post ou mudança no extractor; repetir em massa
    # tende apenas a falhar novamente.
    if 'instagram sent an empty media response' in text:
        return False
    if any(token in text for token in (
        'login required',
        'private post',
        'private video',
        'content is not available',
    )):
        return False

    # Para causas desconhecidas, mantém a possibilidade de nova tentativa.
    return True


def _classify_processing_error(error: str) -> str:
    text = (error or '').casefold()

    if any(token in text for token in ('429', 'rate limit', 'too many requests')):
        return 'Limite temporário da API (429)'
    if any(token in text for token in ('timed out', 'timeout', 'tempo limite')):
        return 'Tempo limite / conexão'
    if any(token in text for token in ('403', 'forbidden', 'login required', 'private video', 'private post')):
        return 'Conteúdo bloqueado, privado ou acesso negado'
    if any(token in text for token in ('401', 'unauthorized', 'invalid api key')):
        return 'Autenticação da API'
    if 'instagram' in text or 'instaloader' in text:
        return 'Falha ao ler conteúdo do Instagram'
    if 'youtube' in text or 'yt-dlp' in text or 'yt_dlp' in text:
        return 'Falha ao extrair vídeo'
    if 'groq' in text:
        return 'Falha na IA / Groq'
    return 'Outros erros'


def _batch_error_groups(items: list[Item]) -> list[dict]:
    groups: dict[str, dict] = {}

    for item in items:
        error = (
            item.jobs.filter(state=ProcessingJob.State.ERROR)
            .order_by('-finished_at', '-id')
            .values_list('error', flat=True)
            .first()
            or 'Erro sem detalhes registrados.'
        )
        label = _classify_processing_error(error)
        retryable = _is_retryable_processing_error(error)
        group = groups.setdefault(
            label,
            {
                'label': label,
                'count': 0,
                'sample': error[:700],
                'items': [],
                'retryable_count': 0,
                'manual_count': 0,
            },
        )
        group['count'] += 1
        if retryable:
            group['retryable_count'] += 1
        else:
            group['manual_count'] += 1
        if len(group['items']) < 6:
            group['items'].append({
                'title': item.title or f'Item #{item.pk}',
                'url': item.get_absolute_url(),
            })

    return sorted(
        groups.values(),
        key=lambda group: group['count'],
        reverse=True,
    )


def home(request):
    mode = request.POST.get('mode', 'single') if request.method == 'POST' else 'single'
    form = CaptureForm(
        request.POST if request.method == 'POST' and mode == 'single' else None
    )
    batch_form = BatchCaptureForm(
        request.POST if request.method == 'POST' and mode == 'batch' else None
    )

    if request.method == 'POST' and mode == 'batch' and batch_form.is_valid():
        created_count = 0
        duplicate_count = 0
        invalid_count = 0
        error_count = 0
        created_ids = []
        batch_id = uuid.uuid4().hex

        for raw in batch_form.cleaned_data['batch_capture']:
            detection = detect_capture(raw)
            if detection.kind == 'note':
                invalid_count += 1
                continue

            try:
                item = create_capture(
                    raw,
                    capture_mode='batch',
                    batch_id=batch_id,
                )
                created_count += 1
                created_ids.append(item.pk)
            except DuplicateCapture:
                duplicate_count += 1
            except Exception:
                error_count += 1

        if created_count:
            request.session['last_batch_ids'] = created_ids
            messages.success(
                request,
                f'{created_count} novo(s) link(s) colocado(s) na fila de processamento.',
            )
        if duplicate_count:
            messages.warning(
                request,
                f'{duplicate_count} link(s) já estavam guardados e foram ignorados.',
                extra_tags='duplicate-warning',
            )
        if invalid_count:
            messages.warning(
                request,
                f'{invalid_count} linha(s) não pareciam links e foram ignoradas.',
            )
        if error_count:
            messages.error(
                request,
                f'{error_count} link(s) não puderam ser adicionados.',
            )

        return redirect('home')

    if request.method == 'POST' and mode == 'single' and form.is_valid():
        action = request.POST.get('action', 'save')

        try:
            item = create_capture(
                form.cleaned_data['capture'],
                form.cleaned_data['title'],
                capture_mode='individual',
            )
        except DuplicateCapture as duplicate:
            item = duplicate.item
            if action == 'save_add_another':
                messages.warning(
                    request,
                    'Este conteúdo já foi guardado. Pode inserir o próximo.',
                    extra_tags='duplicate-warning',
                )
                return redirect('home')

            messages.warning(
                request,
                'Este conteúdo já foi guardado. Abrindo o item existente.',
                extra_tags='duplicate-warning',
            )
            return redirect(item)

        if action == 'save_add_another':
            messages.success(
                request,
                'Conteúdo guardado. Pode inserir o próximo.',
            )
            return redirect('home')

        if item.status == Item.Status.PROCESSING:
            messages.success(
                request,
                'Captura recebida. O processamento começou.',
            )
        else:
            messages.success(request, 'Conteúdo guardado no Segundo Cérebro.')
        return redirect(item)

    recent = Item.objects.all()[:8]

    batch_ids = request.session.get('last_batch_ids', [])
    batch_items = []
    batch_error_items = []

    # Se a sessão já foi limpa, recupera o lote mais recente pelo batch_id
    # persistido nos metadados da captura.
    if not batch_ids:
        latest_batch_item = (
            Item.objects.select_related('source')
            .filter(source__metadata__capture_mode='batch')
            .order_by('-created_at')
            .first()
        )
        latest_batch_id = (
            (latest_batch_item.source.metadata or {}).get('batch_id')
            if latest_batch_item
            else ''
        )
        if latest_batch_id:
            batch_ids = list(
                Item.objects.filter(
                    source__metadata__batch_id=latest_batch_id
                ).values_list('id', flat=True)
            )
            if batch_ids:
                request.session['last_batch_ids'] = batch_ids

    if batch_ids:
        found = {
            item.pk: item
            for item in Item.objects.select_related('source').filter(pk__in=batch_ids)
        }

        # Compatibilidade com lotes criados imediatamente antes desta versão:
        # marca a origem sem exigir que o usuário reenvie os links.
        for item_id in batch_ids:
            item = found.get(item_id)
            if not item:
                continue
            metadata = dict(item.source.metadata or {})
            if not metadata.get('capture_mode'):
                metadata['capture_mode'] = 'batch'
                item.source.metadata = metadata
                item.source.save(update_fields=['metadata'])

        batch_items = [
            found[item_id]
            for item_id in batch_ids
            if item_id in found
            and found[item_id].status == Item.Status.PROCESSING
        ]
        batch_error_items = [
            found[item_id]
            for item_id in batch_ids
            if item_id in found
            and found[item_id].status == Item.Status.ERROR
        ]

        # Sem andamento e sem erros, o lote já não precisa ocupar a home.
        if not batch_items and not batch_error_items:
            request.session.pop('last_batch_ids', None)

    return render(
        request,
        'knowledge/home.html',
        {
            'form': form,
            'batch_form': batch_form,
            'batch_open': mode == 'batch',
            'batch_items': batch_items,
            'batch_error_items': batch_error_items,
            'batch_error_count': len(batch_error_items),
            'batch_error_groups': _batch_error_groups(batch_error_items),
            'recent': recent,
        },
    )


def library(request):
    base_items = (
        Item.objects.all()
        .select_related('source')
        .prefetch_related('tags', 'topics', 'projects')
    )
    q = request.GET.get('q', '').strip()
    item_type = request.GET.get('type', '').strip()
    status = request.GET.get('status', '').strip()
    favorite = request.GET.get('favorite', '').strip()
    search_mode = request.GET.get('search_mode', 'text').strip()
    if search_mode not in {'text', 'semantic'}:
        search_mode = 'text'

    if item_type in Item.Type.values:
        base_items = base_items.filter(type=item_type)
    if status in Item.Status.values:
        base_items = base_items.filter(status=status)
    if favorite == '1':
        base_items = base_items.filter(favorite=True)

    semantic_results = []
    semantic_error = ''

    if q and search_mode == 'semantic':
        allowed_ids = set(base_items.values_list('id', flat=True))
        try:
            semantic_results = semantic_item_results(
                q,
                item_ids=allowed_ids,
                max_items=100,
            )
        except SemanticSearchUnavailable as exc:
            semantic_error = str(exc)
        items = []
    else:
        items = base_items
        if q:
            items = items.filter(
                Q(title__icontains=q)
                | Q(content__icontains=q)
                | Q(summary__icontains=q)
                | Q(source_author__icontains=q)
                | Q(source__caption__icontains=q)
                | Q(source__description__icontains=q)
                | Q(source__transcript__icontains=q)
                | Q(tags__name__icontains=q)
                | Q(topics__name__icontains=q)
                | Q(projects__name__icontains=q)
            ).distinct()
        items = items[:100]

    context = {
        'items': items,
        'semantic_results': semantic_results,
        'semantic_error': semantic_error,
        'search_mode': search_mode,
        'q': q,
        'selected_type': item_type,
        'selected_status': status,
        'favorite': favorite,
        'type_choices': Item.Type.choices,
        'status_choices': Item.Status.choices,
    }
    return render(request, 'knowledge/library.html', context)


def ask_library(request):
    form = AskLibraryForm(request.POST or None)
    result = None
    rag_error = ''

    if request.method == 'POST' and form.is_valid():
        try:
            result = answer_from_library(form.cleaned_data['question'])
        except RagUnavailable as exc:
            rag_error = str(exc)
        except Exception as exc:
            rag_error = f'Não foi possível consultar o acervo: {exc}'

    indexed_chunks = Chunk.objects.exclude(embedding=[]).count()
    indexed_items = (
        Chunk.objects.exclude(embedding=[])
        .values('item_id')
        .distinct()
        .count()
    )

    return render(
        request,
        'knowledge/ask.html',
        {
            'form': form,
            'result': result,
            'rag_error': rag_error,
            'indexed_chunks': indexed_chunks,
            'indexed_items': indexed_items,
        },
    )


def item_detail(request, pk):
    item = get_object_or_404(
        Item.objects.select_related('source').prefetch_related(
            'tags', 'topics', 'projects', 'chunks'
        ),
        pk=pk,
    )

    relations = (
        Relation.objects.filter(
            Q(source=item) | Q(target=item),
            status__in=[Relation.Status.CONFIRMED, Relation.Status.SUGGESTED],
        )
        .select_related('source', 'target')
        .order_by('status', '-confidence', '-created_at')[:30]
    )

    show_content = bool(item.content.strip())
    if (
        item.type == Item.Type.INSTAGRAM
        and item.source.caption
        and item.content.strip() == item.source.caption.strip()
    ):
        show_content = False

    last_error = (
        item.jobs.filter(state=ProcessingJob.State.ERROR)
        .order_by('-finished_at', '-id')
        .values_list('error', flat=True)
        .first()
        or ''
    )

    return render(
        request,
        'knowledge/item_detail.html',
        {
            'item': item,
            'relations': relations,
            'show_content': show_content,
            'last_error': last_error,
        },
    )


def item_progress(request, pk):
    item = get_object_or_404(Item, pk=pk)
    last_error = (
        item.jobs.filter(state='error')
        .order_by('-finished_at', '-id')
        .values_list('error', flat=True)
        .first()
        or ''
    )
    return JsonResponse({
        'id': item.id,
        'title': item.title or 'Sem título',
        'summary': (item.summary or item.content or '')[:180],
        'type_label': item.get_type_display(),
        'status': item.status,
        'status_label': item.get_status_display(),
        'progress': item.processing_progress,
        'stage': item.processing_stage,
        'done': item.processing_progress >= 100,
        'error': last_error[:500] if item.status == Item.Status.ERROR else '',
    })


@require_POST
def toggle_favorite(request, pk):
    item = get_object_or_404(Item, pk=pk)
    item.favorite = not item.favorite
    item.save(update_fields=['favorite', 'updated_at'])
    return HttpResponseRedirect(
        request.META.get('HTTP_REFERER') or item.get_absolute_url()
    )


def _queue_item_retry(item: Item) -> bool:
    """Retoma o item a partir da etapa que realmente falhou."""
    if item.status != Item.Status.ERROR:
        return False

    has_active_job = item.jobs.filter(
        state__in=[
            ProcessingJob.State.PENDING,
            ProcessingJob.State.RUNNING,
        ]
    ).exists()
    if has_active_job:
        return False

    last_failed_job = (
        item.jobs.filter(state=ProcessingJob.State.ERROR)
        .order_by('-finished_at', '-id')
        .first()
    )

    if last_failed_job:
        kind = last_failed_job.kind
    else:
        kind = (
            ProcessingJob.Kind.EXTRACT
            if item.source_url
            else ProcessingJob.Kind.ANALYZE
        )

    ProcessingJob.objects.create(item=item, kind=kind)

    if kind == ProcessingJob.Kind.ANALYZE:
        progress = 70
        stage = 'Aguardando nova análise da IA'
    elif kind == ProcessingJob.Kind.RELATE:
        progress = 92
        stage = 'Aguardando nova análise de conexões'
    else:
        progress = 5
        stage = 'Na fila para tentar novamente a fonte'

    item.status = Item.Status.PROCESSING
    item.processing_progress = progress
    item.processing_stage = stage
    item.save(
        update_fields=[
            'status',
            'processing_progress',
            'processing_stage',
            'updated_at',
        ]
    )
    return True


@require_POST
def retry_item(request, pk):
    item = get_object_or_404(Item, pk=pk)

    if _queue_item_retry(item):
        messages.success(request, 'Nova tentativa colocada na fila.')
    else:
        messages.info(request, 'Este item não está com erro ou já está na fila.')
    return redirect(item)


@require_POST
def retry_last_batch_errors(request):
    batch_ids = request.session.get('last_batch_ids', [])

    if not batch_ids:
        latest_batch_item = (
            Item.objects.select_related('source')
            .filter(source__metadata__capture_mode='batch')
            .order_by('-created_at')
            .first()
        )
        batch_id = (
            (latest_batch_item.source.metadata or {}).get('batch_id')
            if latest_batch_item
            else ''
        )
        if batch_id:
            batch_ids = list(
                Item.objects.filter(
                    source__metadata__batch_id=batch_id
                ).values_list('id', flat=True)
            )
            request.session['last_batch_ids'] = batch_ids

    if not batch_ids:
        messages.info(request, 'Não encontrei um lote recente para tentar novamente.')
        return redirect('home')

    failed_items = list(
        Item.objects.filter(
            pk__in=batch_ids,
            status=Item.Status.ERROR,
        ).order_by('created_at')
    )

    retryable_items = []
    skipped_manual = 0
    for item in failed_items:
        last_error = (
            item.jobs.filter(state=ProcessingJob.State.ERROR)
            .order_by('-finished_at', '-id')
            .values_list('error', flat=True)
            .first()
            or ''
        )
        if _is_retryable_processing_error(last_error):
            retryable_items.append(item)
        else:
            skipped_manual += 1

    queued = sum(1 for item in retryable_items if _queue_item_retry(item))

    if queued:
        messages.success(
            request,
            f'{queued} item(ns) com erro transitório voltaram para a fila.',
        )
    elif not failed_items:
        messages.info(request, 'Não há itens com erro neste lote.')
    else:
        messages.info(
            request,
            'Os erros restantes exigem atenção manual e não foram repetidos automaticamente.',
        )

    if skipped_manual:
        messages.warning(
            request,
            f'{skipped_manual} item(ns) foram mantidos com erro porque repetir automaticamente provavelmente não resolveria.',
        )

    return redirect('home')


@require_POST
def reprocess_item(request, pk):
    item = get_object_or_404(Item, pk=pk)

    if not item.source_url:
        messages.info(request, 'Este item não possui uma fonte para reprocessar.')
        return redirect(item)

    has_active_job = item.jobs.filter(
        state__in=[ProcessingJob.State.PENDING, ProcessingJob.State.RUNNING]
    ).exists()
    if has_active_job:
        messages.info(request, 'Este item já está sendo processado.')
        return redirect(item)

    # A extração pode enriquecer o conteúdo (ex.: OCR de slides).
    # Limpamos somente a análise automática para que ela seja refeita.
    item.analysis = {}
    item.summary = ''
    item.status = Item.Status.PROCESSING
    item.processing_progress = 5
    item.processing_stage = 'Na fila para reprocessar'
    item.save(
        update_fields=[
            'analysis',
            'summary',
            'status',
            'processing_progress',
            'processing_stage',
            'updated_at',
        ]
    )
    item.topics.clear()
    item.tags.clear()

    ProcessingJob.objects.create(
        item=item,
        kind=ProcessingJob.Kind.EXTRACT,
    )

    messages.success(request, 'Reprocessamento colocado na fila.')
    return redirect(item)


@require_POST
def confirm_relation(request, pk):
    relation = get_object_or_404(Relation, pk=pk)
    relation.status = Relation.Status.CONFIRMED
    relation.save(update_fields=['status'])
    messages.success(request, 'Relação confirmada.')
    return HttpResponseRedirect(
        request.META.get('HTTP_REFERER') or relation.source.get_absolute_url()
    )


@require_POST
def unconfirm_relation(request, pk):
    relation = get_object_or_404(Relation, pk=pk)
    relation.status = Relation.Status.SUGGESTED
    relation.save(update_fields=['status'])
    messages.info(request, 'Confirmação desfeita. A relação voltou para sugestões.')
    return HttpResponseRedirect(
        request.META.get('HTTP_REFERER') or relation.source.get_absolute_url()
    )


@require_POST
def reject_relation(request, pk):
    relation = get_object_or_404(Relation, pk=pk)
    relation.status = Relation.Status.REJECTED
    relation.save(update_fields=['status'])
    messages.info(request, 'Conexão removida. Ela não será sugerida novamente.')
    return HttpResponseRedirect(
        request.META.get('HTTP_REFERER') or relation.source.get_absolute_url()
    )


def connections(request):
    active_relations = (
        Relation.objects.filter(
            status__in=[
                Relation.Status.CONFIRMED,
                Relation.Status.SUGGESTED,
            ]
        )
        .select_related('source', 'target')
        .order_by('-confidence', '-created_at')[:250]
    )
    analyzed_items = Item.objects.exclude(analysis={}).count()

    return render(
        request,
        'knowledge/connections.html',
        {
            'active_relations': active_relations,
            'analyzed_items': analyzed_items,
            'connection_count': active_relations.count(),
        },
    )
