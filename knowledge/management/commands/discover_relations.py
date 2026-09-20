from django.core.management.base import BaseCommand, CommandError

from knowledge.models import Item
from knowledge.services.relations import (
    RelationDiscoverySkipped,
    discover_relations,
)


class Command(BaseCommand):
    help = 'Procura relações automáticas entre itens já analisados.'

    def add_arguments(self, parser):
        parser.add_argument('--item', type=int, help='Analisa somente um item específico.')

    def handle(self, *args, **options):
        qs = Item.objects.exclude(analysis={}).select_related('source')

        if options['item']:
            qs = qs.filter(pk=options['item'])
            if not qs.exists():
                raise CommandError('Item não encontrado ou ainda sem análise.')

        total = qs.count()
        if total == 0:
            self.stdout.write('Nenhum item analisado disponível para relações.')
            return

        created_total = skipped = failed = 0

        for item in qs.iterator():
            self.stdout.write(f'[{item.pk}] {item.title or item.get_type_display()}')
            try:
                created = discover_relations(item)
                created_total += len(created)
                if created:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'  ✓ {len(created)} sugestão(ões) criada(s)'
                        )
                    )
                else:
                    self.stdout.write('  · nenhum candidato forte')
            except RelationDiscoverySkipped as exc:
                skipped += 1
                self.stdout.write(self.style.WARNING(f'  ↷ pulado: {exc}'))
            except Exception as exc:
                failed += 1
                self.stderr.write(self.style.ERROR(f'  ✗ erro: {exc}'))

        self.stdout.write(
            self.style.SUCCESS(
                f'Fim: {created_total} sugestão(ões), {skipped} pulado(s), {failed} erro(s).'
            )
        )
