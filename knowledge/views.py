from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import CaptureForm
from .models import Item, Relation
from .services.capture import create_capture


def home(request):
    form = CaptureForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        item = create_capture(form.cleaned_data['capture'], form.cleaned_data['title'])
        if item.status == Item.Status.PROCESSED:
            messages.success(request, 'Conteúdo já está no Segundo Cérebro.')
        elif item.jobs.filter(state='pending').exists():
            messages.success(request, 'Captura recebida. Ela entrou na fila de processamento.')
        else:
            messages.info(request, 'Esse conteúdo já havia sido capturado.')
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

    relations = Relation.objects.filter(
        Q(source=item) | Q(target=item),
        status__in=[Relation.Status.CONFIRMED, Relation.Status.SUGGESTED],
    ).select_related('source', 'target')[:30]

    show_content = bool(item.content.strip())
    if (
        item.type == Item.Type.INSTAGRAM
        and item.source.caption
        and item.content.strip() == item.source.caption.strip()
    ):
        show_content = False

    return render(
        request,
        'knowledge/item_detail.html',
        {'item': item, 'relations': relations, 'show_content': show_content},
    )


@require_POST
def toggle_favorite(request, pk):
    item = get_object_or_404(Item, pk=pk)
    item.favorite = not item.favorite
    item.save(update_fields=['favorite', 'updated_at'])
    return HttpResponseRedirect(
        request.META.get('HTTP_REFERER') or item.get_absolute_url()
    )


def connections(request):
    relations = (
        Relation.objects.filter(status=Relation.Status.CONFIRMED)
        .select_related('source', 'target')[:250]
    )
    return render(request, 'knowledge/connections.html', {'relations': relations})
