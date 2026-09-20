import time
from django.core.management.base import BaseCommand
from knowledge.services.jobs import claim_next_job, process_job

class Command(BaseCommand):
    help = 'Processa continuamente a fila de capturas sem depender de Redis/Celery.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true', help='Processa no máximo um job e encerra.')
        parser.add_argument('--sleep', type=float, default=2.0, help='Segundos entre verificações quando a fila está vazia.')

    def handle(self, *args, **options):
        while True:
            job = claim_next_job()
            if job:
                self.stdout.write(f'Processando job {job.pk} / item {job.item_id}...')
                try:
                    process_job(job)
                    self.stdout.write(self.style.SUCCESS(f'Job {job.pk} concluído.'))
                except Exception as exc:
                    self.stderr.write(self.style.ERROR(f'Job {job.pk} falhou: {exc}'))
            elif options['once']:
                return
            else:
                time.sleep(options['sleep'])
            if options['once']:
                return
