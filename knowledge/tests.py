from django.test import TestCase
from .models import Item, ProcessingJob
from .services.capture import create_capture
from .services.detector import detect_capture

class DetectorTests(TestCase):
    def test_instagram(self):
        self.assertEqual(detect_capture('https://www.instagram.com/reel/ABC/').kind, 'instagram')

    def test_youtube(self):
        self.assertEqual(detect_capture('https://youtu.be/abc').kind, 'youtube')

    def test_web(self):
        self.assertEqual(detect_capture('https://example.com/artigo').kind, 'web')

    def test_note(self):
        self.assertEqual(detect_capture('lembrar de testar pgvector').kind, 'note')

class CaptureTests(TestCase):
    def test_note_is_ready_immediately(self):
        item = create_capture('Uma nota simples', 'Minha nota')
        self.assertEqual(item.type, Item.Type.NOTE)
        self.assertEqual(item.status, Item.Status.PROCESSED)
        self.assertFalse(ProcessingJob.objects.exists())

    def test_url_is_queued(self):
        item = create_capture('https://www.instagram.com/reel/ABC/')
        self.assertEqual(item.type, Item.Type.INSTAGRAM)
        self.assertEqual(item.status, Item.Status.PROCESSING)
        self.assertTrue(ProcessingJob.objects.filter(item=item).exists())
