from django.test import TestCase, override_settings

from .models import Item, ProcessingJob
from .services.capture import DuplicateCapture, create_capture
from .services.detector import detect_capture


class DetectorTests(TestCase):
    def test_instagram(self):
        detection = detect_capture(
            'https://www.instagram.com/reel/ABC/?stkn=tracking'
        )
        self.assertEqual(detection.kind, 'instagram')
        self.assertEqual(
            detection.normalized,
            'https://www.instagram.com/reel/ABC/',
        )

    def test_youtube(self):
        detection = detect_capture('https://youtu.be/abc?t=12')
        self.assertEqual(detection.kind, 'youtube')
        self.assertEqual(
            detection.normalized,
            'https://www.youtube.com/watch?v=abc',
        )

    def test_web_strips_tracking_params(self):
        detection = detect_capture(
            'https://example.com/artigo?utm_source=x&id=7&fbclid=abc'
        )
        self.assertEqual(
            detection.normalized,
            'https://example.com/artigo?id=7',
        )

    def test_note(self):
        self.assertEqual(
            detect_capture('lembrar de testar pgvector').kind,
            'note',
        )


class CaptureTests(TestCase):
    @override_settings(ANALYZE_CONTENT=True, GROQ_API_KEY='test-key')
    def test_note_queues_analysis_and_progress(self):
        item = create_capture('Uma nota simples', 'Minha nota')
        self.assertEqual(item.type, Item.Type.NOTE)
        self.assertEqual(item.status, Item.Status.PROCESSING)
        self.assertEqual(item.processing_progress, 70)
        job = ProcessingJob.objects.get(item=item)
        self.assertEqual(job.kind, ProcessingJob.Kind.ANALYZE)

    def test_url_is_queued_for_extraction(self):
        item = create_capture(
            'https://www.instagram.com/reel/ABC/?stkn=qualquer'
        )
        self.assertEqual(item.type, Item.Type.INSTAGRAM)
        self.assertEqual(item.status, Item.Status.PROCESSING)
        self.assertEqual(item.processing_progress, 5)
        self.assertEqual(
            item.source_url,
            'https://www.instagram.com/reel/ABC/',
        )
        job = ProcessingJob.objects.get(item=item)
        self.assertEqual(job.kind, ProcessingJob.Kind.EXTRACT)

    def test_same_instagram_is_rejected(self):
        first = create_capture(
            'https://www.instagram.com/reel/ABC/?stkn=um'
        )
        with self.assertRaises(DuplicateCapture) as ctx:
            create_capture(
                'https://instagram.com/reel/ABC/?utm_source=dois'
            )
        self.assertEqual(ctx.exception.item.pk, first.pk)
        self.assertEqual(Item.objects.count(), 1)

    def test_same_web_url_with_tracking_is_rejected(self):
        first = create_capture(
            'https://example.com/artigo?id=7&utm_source=newsletter'
        )
        with self.assertRaises(DuplicateCapture) as ctx:
            create_capture(
                'https://example.com/artigo?fbclid=abc&id=7'
            )
        self.assertEqual(ctx.exception.item.pk, first.pk)
        self.assertEqual(Item.objects.count(), 1)
