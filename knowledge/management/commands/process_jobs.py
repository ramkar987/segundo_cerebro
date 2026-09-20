import os
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from knowledge.models import ProcessingJob
from knowledge.services.jobs import claim_next_job, process_job



class WorkerAlreadyRunning(Exception):
    pass


class SingleWorkerLock:
    """Lock de processo, liberado automaticamente pelo SO ao encerrar."""

    def __init__(self):
        self.path = Path(settings.BASE_DIR) / '.process_jobs.lock'
        self.handle = None

    def __enter__(self):
        self.path.touch(exist_ok=True)
        self.handle = self.path.open('r+')

        if os.name == 'nt':
            import msvcrt

            try:
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                self.handle.close()
                self.handle = None
                raise WorkerAlreadyRunning from exc
        else:
            import fcntl

            try:
                fcntl.flock(
                    self.handle.fileno(),
                    fcntl.LOCK_EX | fcntl.LOCK_NB,
                )
            except OSError as exc:
                self.handle.close()
                self.handle = None
                raise WorkerAlreadyRunning from exc

        self.handle.seek(0)
        self.handle.truncate()
        self.handle.write(str(os.getpid()))
        self.handle.flush()
        return self

    def __exit__(self, exc_type, exc, tb):
        if not self.handle:
            return

        try:
            if os.name == 'nt':
                import msvcrt

                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()


class Command(BaseCommand):
    help = 'Processa continuamente a fila de capturas sem depender de Redis/Celery.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--once',
            action='store_true',
            help='Processa no máximo um job e encerra.',
        )
        parser.add_argument(
            '--sleep',
            type=float,
            default=2.0,
            help='Segundos entre verificações quando a fila está vazia.',
        )

    def handle(self, *args, **options):
        try:
            with SingleWorkerLock():
                return self._run_worker(options)
        except WorkerAlreadyRunning:
            self.stdout.write(
                self.style.WARNING(
                    'Já existe um worker do Segundo Cérebro rodando. '
                    'Esta instância será encerrada.'
                )
            )
            return

    def _run_worker(self, options):
        # Nesta V1 usamos um único worker. Se ele foi interrompido no meio de
        # um job, recuperamos automaticamente a fila na reinicialização.
        recovered = ProcessingJob.objects.filter(
            state=ProcessingJob.State.RUNNING
        ).update(
            state=ProcessingJob.State.PENDING,
            started_at=None,
        )
        if recovered:
            self.stdout.write(
                self.style.WARNING(
                    f'{recovered} job(s) interrompido(s) devolvido(s) à fila.'
                )
            )

        while True:
            job = claim_next_job()
            if job:
                self.stdout.write(
                    f'Processando job {job.pk} / item {job.item_id} '
                    f'({job.get_kind_display()})...'
                )
                try:
                    process_job(job)
                    self.stdout.write(
                        self.style.SUCCESS(f'Job {job.pk} concluído.')
                    )
                except Exception as exc:
                    self.stderr.write(
                        self.style.ERROR(f'Job {job.pk} falhou: {exc}')
                    )
            elif options['once']:
                return
            else:
                time.sleep(options['sleep'])

            if options['once']:
                return
