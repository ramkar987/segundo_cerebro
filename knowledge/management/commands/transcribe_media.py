from django.core.management.base import BaseCommand, CommandError

from knowledge.models import Item
from knowledge.services.transcription import (
    TranscriptionSkipped,
    mark_transcription_state,
    transcribe_item,
)


class Command(BaseCommand):
    help = 'Transcreve mídias Instagram/YouTube já cadastradas e ainda sem transcrição.'

    def add_arguments(self, parser):
        parser.add_argument('--item', type=int, help='Transcreve somente um item específico.')
        parser.add_argument('--force', action='store_true', help='Retranscreve mesmo quando já existe transcrição.')

    def handle(self, *args, **options):
        qs = Item.objects.filter(type__in=[Item.Type.INSTAGRAM, Item.Type.YOUTUBE]).select_related('source')

        if options['item']:
            qs = qs.filter(pk=options['item'])
            if not qs.exists():
                raise CommandError('Item não encontrado ou não é Instagram/YouTube.')

        if not options['force']:
            qs = qs.filter(source__transcript='')

        total = qs.count()
        if total == 0:
            self.stdout.write('Nenhuma mídia pendente de transcrição.')
            return

        self.stdout.write(f'{total} mídia(s) para transcrever.')

        ok = skipped = failed = 0
        for item in qs.iterator():
            self.stdout.write(f'[{item.pk}] {item.title or item.source_url}')
            try:
                transcript = transcribe_item(item)
                ok += 1
                self.stdout.write(self.style.SUCCESS(f'  ✓ {len(transcript)} caracteres transcritos'))
            except TranscriptionSkipped as exc:
                skipped += 1
                mark_transcription_state(item, 'skipped', str(exc))
                self.stdout.write(self.style.WARNING(f'  ↷ pulado: {exc}'))
            except Exception as exc:
                failed += 1
                mark_transcription_state(item, 'error', str(exc))
                self.stderr.write(self.style.ERROR(f'  ✗ erro: {exc}'))

        self.stdout.write(
            self.style.SUCCESS(
                f'Fim: {ok} transcrita(s), {skipped} pulada(s), {failed} erro(s).'
            )
        )
