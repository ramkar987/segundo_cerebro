from django.core.management.base import BaseCommand, CommandError

from knowledge.models import Item
from knowledge.services.semantic import SemanticIndexSkipped, index_item


class Command(BaseCommand):
    help = 'Cria/recria chunks e embeddings para busca semântica e RAG.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--item',
            type=int,
            help='Indexa somente um item específico.',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Refaz embeddings mesmo quando o item já está indexado.',
        )

    def handle(self, *args, **options):
        qs = Item.objects.select_related('source').exclude(
            status__in=[
                Item.Status.ERROR,
                Item.Status.PROCESSING,
            ]
        )

        if options['item']:
            qs = qs.filter(pk=options['item'])
            if not qs.exists():
                raise CommandError('Item não encontrado.')

        total = qs.count()
        if not total:
            self.stdout.write('Nenhum item disponível para indexação.')
            return

        self.stdout.write(f'{total} item(ns) para verificar.')

        ok = skipped = failed = 0

        for item in qs.iterator():
            self.stdout.write(
                f'[{item.pk}] {item.title or item.get_type_display()}'
            )
            try:
                count = index_item(item, force=options['force'])
                ok += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f'  ✓ {count} trecho(s) indexado(s)'
                    )
                )
            except SemanticIndexSkipped as exc:
                skipped += 1
                self.stdout.write(
                    self.style.WARNING(f'  ↷ pulado: {exc}')
                )
            except Exception as exc:
                failed += 1
                self.stderr.write(
                    self.style.ERROR(f'  ✗ erro: {exc}')
                )

        self.stdout.write(
            self.style.SUCCESS(
                f'Fim: {ok} indexado(s), {skipped} pulado(s), '
                f'{failed} erro(s).'
            )
        )
