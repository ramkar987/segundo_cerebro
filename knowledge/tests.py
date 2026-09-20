from django.test import TestCase, override_settings

from .forms import BatchCaptureForm
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

    def test_instagram_without_protocol(self):
        detection = detect_capture(
            'www.instagram.com/reel/DdbK8N-uFUj/?stkn=tracking'
        )
        self.assertEqual(detection.kind, 'instagram')
        self.assertEqual(
            detection.normalized,
            'https://www.instagram.com/reel/DdbK8N-uFUj/',
        )

    def test_instagram_without_www_or_protocol(self):
        detection = detect_capture(
            'instagram.com/reel/DdbK8N-uFUj/'
        )
        self.assertEqual(detection.kind, 'instagram')
        self.assertEqual(
            detection.normalized,
            'https://www.instagram.com/reel/DdbK8N-uFUj/',
        )

    def test_youtube(self):
        detection = detect_capture('https://youtu.be/abc?t=12')
        self.assertEqual(detection.kind, 'youtube')
        self.assertEqual(
            detection.normalized,
            'https://www.youtube.com/watch?v=abc',
        )

    def test_youtube_without_protocol(self):
        detection = detect_capture('youtu.be/abc?t=12')
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

    def test_web_without_protocol(self):
        detection = detect_capture(
            'example.com/artigo?utm_source=x&id=7'
        )
        self.assertEqual(detection.kind, 'web')
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
            'www.instagram.com/reel/ABC/?stkn=qualquer'
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

    def test_same_instagram_is_rejected_even_without_protocol(self):
        first = create_capture(
            'https://www.instagram.com/reel/ABC/?stkn=um'
        )
        with self.assertRaises(DuplicateCapture) as ctx:
            create_capture(
                'instagram.com/reel/ABC/?utm_source=dois'
            )
        self.assertEqual(ctx.exception.item.pk, first.pk)
        self.assertEqual(Item.objects.count(), 1)

    def test_same_web_url_with_tracking_is_rejected(self):
        first = create_capture(
            'https://example.com/artigo?id=7&utm_source=newsletter'
        )
        with self.assertRaises(DuplicateCapture) as ctx:
            create_capture(
                'example.com/artigo?fbclid=abc&id=7'
            )
        self.assertEqual(ctx.exception.item.pk, first.pk)
        self.assertEqual(Item.objects.count(), 1)



class BatchCaptureFormTests(TestCase):
    def test_accepts_numbered_and_bulleted_links(self):
        form = BatchCaptureForm({
            'batch_capture': (
                '1. https://example.com/a\n'
                '• www.instagram.com/p/ABC/\n'
                '- https://youtu.be/xyz'
            )
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.cleaned_data['batch_capture'],
            [
                'https://example.com/a',
                'www.instagram.com/p/ABC/',
                'https://youtu.be/xyz',
            ],
        )

    def test_limits_batch_to_100_lines(self):
        form = BatchCaptureForm({
            'batch_capture': '\n'.join(
                f'https://example.com/{index}'
                for index in range(101)
            )
        })
        self.assertFalse(form.is_valid())


class BatchCaptureViewTests(TestCase):
    def test_batch_creates_valid_links_and_ignores_duplicate_and_text(self):
        response = self.client.post(
            '/',
            {
                'mode': 'batch',
                'batch_capture': (
                    'https://example.com/a\n'
                    'https://example.com/a\n'
                    'isto não é um link'
                ),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/')
        self.assertEqual(Item.objects.count(), 1)
        self.assertEqual(ProcessingJob.objects.count(), 1)

    def test_save_and_add_another_returns_to_capture(self):
        response = self.client.post(
            '/',
            {
                'mode': 'single',
                'capture': 'https://example.com/novo',
                'title': '',
                'action': 'save_add_another',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/')
        self.assertEqual(Item.objects.count(), 1)
