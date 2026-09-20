from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import CaptureForm
from .models import Item, ProcessingJob, Relation
from .services.capture import DuplicateCapture, create_capture


def home(request):
    form = CaptureForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            item = create_capture(
                form.cleaned_data['capture'],
                form.cleaned_data['title'],
            )
        except DuplicateCapture as duplicate:
            item = duplicate.item
            messages.warning(
                request,
                'Este conteúdo já foi guardado. Abrindo o item existente.',
            )
            return redirect(item)

        if item.status == Item.Status.PROCESSING:
            messages.success(
                request,
                'Captura recebida. O processamento começou.',
            )
        else:
            messages.success(request, 'Conteúdo guardado no Segundo Cérebro.')
        return redirect(item)

    recent = Item.objects.all()[:8]
    return render(request, 'knowledge/home.html', {'form': form, 'recent': recent})


def library(request):
    items = (
        Item.objects.all()
        .select_related('source')
        .prefetch_related('tags', 'topics', 'projects')
    )
    q = request.GET.get('q', '').strip()
    item_type = request.GET.get('type', '').strip()
    status = request.GET.get('status', '').strip()
    favorite = request.GET.get('favorite', '').strip()

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

    if item_type in Item.Type.values:
        items = items.filter(type=item_type)
    if status in Item.Status.values:
        items = items.filter(status=status)
    if favorite == '1':
        items = items.filter(favorite=True)

    context = {
        'items': items[:100],
        'q': q,
        'selected_type': item_type,
        'selected_status': status,
        'favorite': favorite,
        'type_choices': Item.Type.choices,
        'status_choices': Item.Status.choices,
    }
    return render(request, 'knowledge/library.html', context)


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


@require_POST
def retry_item(request, pk):
    item = get_object_or_404(Item, pk=pk)

    if item.status != Item.Status.ERROR:
        messages.info(request, 'Este item não está com erro.')
        return redirect(item)

    has_active_job = item.jobs.filter(
        state__in=[ProcessingJob.State.PENDING, ProcessingJob.State.RUNNING]
    ).exists()

    if not has_active_job:
        kind = (
            ProcessingJob.Kind.EXTRACT
            if item.source_url
            else ProcessingJob.Kind.ANALYZE
        )
        ProcessingJob.objects.create(item=item, kind=kind)

    item.status = Item.Status.PROCESSING
    item.processing_progress = 5 if item.source_url else 70
    item.processing_stage = (
        'Na fila para tentar novamente'
        if item.source_url
        else 'Aguardando nova análise da IA'
    )
    item.save(
        update_fields=[
            'status',
            'processing_progress',
            'processing_stage',
            'updated_at',
        ]
    )

    messages.success(request, 'Nova tentativa colocada na fila.')
    return redirect(item)


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
def reject_relation(request, pk):
    relation = get_object_or_404(Relation, pk=pk)
    relation.status = Relation.Status.REJECTED
    relation.save(update_fields=['status'])
    messages.info(request, 'Sugestão de relação rejeitada.')
    return HttpResponseRedirect(
        request.META.get('HTTP_REFERER') or relation.source.get_absolute_url()
    )


def connections(request):
    confirmed = (
        Relation.objects.filter(status=Relation.Status.CONFIRMED)
        .select_related('source', 'target')
        .order_by('-created_at')[:250]
    )
    suggested = (
        Relation.objects.filter(status=Relation.Status.SUGGESTED)
        .select_related('source', 'target')
        .order_by('-confidence', '-created_at')[:100]
    )
    analyzed_items = Item.objects.exclude(analysis={}).count()

    return render(
        request,
        'knowledge/connections.html',
        {
            'confirmed_relations': confirmed,
            'suggested_relations': suggested,
            'analyzed_items': analyzed_items,
            'confirmed_count': confirmed.count(),
            'suggested_count': suggested.count(),
        },
    )
