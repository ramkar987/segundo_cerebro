from django.test import TestCase

from .models import Item, ProcessingJob
from .services.capture import create_capture
from .services.detector import detect_capture


class DetectorTests(TestCase):
    def test_instagram(self):
        detection = detect_capture('https://www.instagram.com/reel/ABC/?stkn=tracking')
        self.assertEqual(detection.kind, 'instagram')
        self.assertEqual(detection.normalized, 'https://www.instagram.com/reel/ABC/')

    def test_youtube(self):
        detection = detect_capture('https://youtu.be/abc?t=12')
        self.assertEqual(detection.kind, 'youtube')
        self.assertEqual(detection.normalized, 'https://www.youtube.com/watch?v=abc')

    def test_web(self):
        self.assertEqual(detect_capture('https://example.com/artigo').kind, 'web')

    def test_note(self):
        self.assertEqual(detect_capture('lembrar de testar pgvector').kind, 'note')


class CaptureTests(TestCase):
    def test_note_is_ready_and_analysis_is_queued(self):
        item = create_capture('Uma nota simples', 'Minha nota')
        self.assertEqual(item.type, Item.Type.NOTE)
        self.assertEqual(item.status, Item.Status.PROCESSED)
        job = ProcessingJob.objects.get(item=item)
        self.assertEqual(job.kind, ProcessingJob.Kind.ANALYZE)

    def test_url_is_queued_for_extraction(self):
        item = create_capture('https://www.instagram.com/reel/ABC/?stkn=qualquer')
        self.assertEqual(item.type, Item.Type.INSTAGRAM)
        self.assertEqual(item.status, Item.Status.PROCESSING)
        self.assertEqual(item.source_url, 'https://www.instagram.com/reel/ABC/')
        job = ProcessingJob.objects.get(item=item)
        self.assertEqual(job.kind, ProcessingJob.Kind.EXTRACT)

    def test_same_instagram_is_not_duplicated(self):
        first = create_capture('https://www.instagram.com/reel/ABC/?stkn=um')
        second = create_capture('https://instagram.com/reel/ABC/?utm_source=dois')
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Item.objects.count(), 1)
