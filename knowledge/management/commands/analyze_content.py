from django.core.management.base import BaseCommand, CommandError

from knowledge.models import Item
from knowledge.services.analysis import AnalysisSkipped, analyze_item


class Command(BaseCommand):
    help = 'Analisa itens já cadastrados com IA e gera resumo, tags e assunto.'

    def add_arguments(self, parser):
        parser.add_argument('--item', type=int, help='Analisa somente um item específico.')
        parser.add_argument('--force', action='store_true', help='Refaz análise mesmo quando já existe.')

    def handle(self, *args, **options):
        qs = Item.objects.select_related('source').all()

        if options['item']:
            qs = qs.filter(pk=options['item'])
            if not qs.exists():
                raise CommandError('Item não encontrado.')

        if not options['force']:
            qs = qs.filter(analysis={})

        total = qs.count()
        if total == 0:
            self.stdout.write('Nenhum item pendente de análise.')
            return

        self.stdout.write(f'{total} item(ns) para analisar.')

        ok = skipped = failed = 0
        for item in qs.iterator():
            self.stdout.write(f'[{item.pk}] {item.title or item.get_type_display()}')
            try:
                data = analyze_item(item)
                ok += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  ✓ {data.get('topic') or 'sem assunto'} · "
                        f"{len(data.get('tags') or [])} tag(s)"
                    )
                )
            except AnalysisSkipped as exc:
                skipped += 1
                self.stdout.write(self.style.WARNING(f'  ↷ pulado: {exc}'))
            except Exception as exc:
                failed += 1
                self.stderr.write(self.style.ERROR(f'  ✗ erro: {exc}'))

        self.stdout.write(
            self.style.SUCCESS(
                f'Fim: {ok} analisado(s), {skipped} pulado(s), {failed} erro(s).'
            )
        )
