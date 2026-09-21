from unittest.mock import Mock, patch

from django.test import TestCase, override_settings

from .forms import BatchCaptureForm
from .models import Chunk, Item, ItemSource, ProcessingJob
from .services.capture import DuplicateCapture, create_capture
from .services.detector import detect_capture
from .services.rag import answer_from_library
from .services.semantic import SemanticHit, build_chunks, semantic_search, split_text


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


    def test_retry_resumes_failed_analysis_without_reextracting(self):
        item = Item.objects.create(
            type=Item.Type.INSTAGRAM,
            title='Instagram já extraído',
            source_url='https://www.instagram.com/reel/ABC/',
            status=Item.Status.ERROR,
            processing_progress=100,
        )
        ItemSource.objects.create(
            item=item,
            platform='instagram',
            metadata={},
        )
        ProcessingJob.objects.create(
            item=item,
            kind=ProcessingJob.Kind.EXTRACT,
            state=ProcessingJob.State.DONE,
        )
        ProcessingJob.objects.create(
            item=item,
            kind=ProcessingJob.Kind.ANALYZE,
            state=ProcessingJob.State.ERROR,
            error='Groq retornou HTTP 429',
        )

        response = self.client.post(
            f'/item/{item.pk}/tentar-novamente/'
        )

        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.status, Item.Status.PROCESSING)
        self.assertEqual(item.processing_progress, 70)

        pending = item.jobs.filter(
            state=ProcessingJob.State.PENDING
        ).latest('id')
        self.assertEqual(pending.kind, ProcessingJob.Kind.ANALYZE)


    def test_retry_last_batch_errors_requeues_only_that_batch(self):
        batch_error = Item.objects.create(
            type=Item.Type.WEB,
            title='Erro do lote',
            source_url='https://example.com/erro-lote',
            status=Item.Status.ERROR,
            processing_progress=100,
        )
        ItemSource.objects.create(
            item=batch_error,
            platform='web',
            metadata={
                'capture_mode': 'batch',
                'batch_id': 'lote-atual',
            },
        )

        other_error = Item.objects.create(
            type=Item.Type.WEB,
            title='Erro de outro lote',
            source_url='https://example.com/outro-erro',
            status=Item.Status.ERROR,
            processing_progress=100,
        )
        ItemSource.objects.create(
            item=other_error,
            platform='web',
            metadata={
                'capture_mode': 'batch',
                'batch_id': 'lote-antigo',
            },
        )

        session = self.client.session
        session['last_batch_ids'] = [batch_error.pk]
        session.save()

        response = self.client.post('/lote/tentar-erros-novamente/')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/')

        batch_error.refresh_from_db()
        other_error.refresh_from_db()

        self.assertEqual(batch_error.status, Item.Status.PROCESSING)
        self.assertEqual(other_error.status, Item.Status.ERROR)

        job = ProcessingJob.objects.get(item=batch_error)
        self.assertEqual(job.kind, ProcessingJob.Kind.EXTRACT)
        self.assertEqual(job.state, ProcessingJob.State.PENDING)



class SemanticSearchTests(TestCase):
    def setUp(self):
        self.item = Item.objects.create(
            type=Item.Type.NOTE,
            title='Experimento com cinco dólares',
            content=(
                'Uma professora entregou cinco dólares para grupos e propôs '
                'que encontrassem maneiras de gerar valor em pouco tempo.'
            ),
            status=Item.Status.PROCESSED,
        )
        ItemSource.objects.create(
            item=self.item,
            platform='manual',
            metadata={},
        )

    def test_split_text_respects_reasonable_chunk_size(self):
        text = ('Primeira frase. ' * 80) + '\n\n' + ('Segunda frase. ' * 80)
        chunks = split_text(text, max_chars=300)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 340 for chunk in chunks))

    def test_build_chunks_uses_original_note_content(self):
        chunks = build_chunks(self.item)
        self.assertGreaterEqual(len(chunks), 1)
        self.assertEqual(chunks[0].kind, Chunk.Kind.CONTENT)
        self.assertIn('cinco dólares', chunks[0].text)

    @patch(
        'knowledge.services.semantic.embed_query',
        return_value=[1.0, 0.0],
    )
    def test_semantic_search_orders_by_cosine_similarity(self, _mock_embed):
        first = Chunk.objects.create(
            item=self.item,
            kind=Chunk.Kind.CONTENT,
            text='mais próximo',
            position=0,
            embedding=[1.0, 0.0],
        )
        other_item = Item.objects.create(
            type=Item.Type.NOTE,
            title='Outro',
            content='Outro conteúdo',
            status=Item.Status.PROCESSED,
        )
        ItemSource.objects.create(
            item=other_item,
            platform='manual',
            metadata={},
        )
        Chunk.objects.create(
            item=other_item,
            kind=Chunk.Kind.CONTENT,
            text='menos próximo',
            position=0,
            embedding=[0.0, 1.0],
        )

        with override_settings(SEMANTIC_MIN_SCORE=-1.0, SEMANTIC_TOP_K=10):
            hits = semantic_search('consulta')

        self.assertEqual(hits[0].chunk.pk, first.pk)
        self.assertGreater(hits[0].score, hits[1].score)


class RagTests(TestCase):
    @override_settings(
        GROQ_API_KEY='test-key',
        GROQ_CHAT_MODEL='test-model',
        RAG_CANDIDATE_TOP_K=12,
        RAG_TOP_K=5,
        RAG_MAX_CHUNKS_PER_ITEM=2,
        RAG_RELATIVE_SCORE_DROP=0.12,
        SEMANTIC_MIN_SCORE=0.20,
        AI_TIMEOUT=5,
    )
    @patch('knowledge.services.rag.requests.post')
    @patch('knowledge.services.rag.semantic_search')
    def test_rag_returns_only_approved_used_source(
        self,
        mock_search,
        mock_post,
    ):
        item = Item.objects.create(
            type=Item.Type.NOTE,
            title='Minha nota',
            content='Conteúdo de teste',
            status=Item.Status.PROCESSED,
        )
        ItemSource.objects.create(item=item, platform='manual', metadata={})
        chunk = Chunk.objects.create(
            item=item,
            kind=Chunk.Kind.CONTENT,
            text='O trecho exato que sustenta a resposta.',
            position=0,
            embedding=[1.0, 0.0],
        )
        mock_search.return_value = [SemanticHit(chunk=chunk, score=0.9)]

        gate_response = Mock()
        gate_response.status_code = 200
        gate_response.json.return_value = {
            'choices': [
                {
                    'message': {
                        'content': '{"relevant_sources":[1]}'
                    }
                }
            ]
        }

        answer_response = Mock()
        answer_response.status_code = 200
        answer_response.json.return_value = {
            'choices': [
                {
                    'message': {
                        'content': (
                            '{"answer":"Resposta baseada no acervo [1].",'
                            '"used_sources":[1]}'
                        )
                    }
                }
            ]
        }

        mock_post.side_effect = [gate_response, answer_response]

        result = answer_from_library('O que eu guardei?')

        self.assertEqual(result['answer'], 'Resposta baseada no acervo [1].')
        self.assertEqual(len(result['sources']), 1)
        self.assertEqual(result['sources'][0]['item'].pk, item.pk)
        self.assertEqual(mock_post.call_count, 2)

    @override_settings(
        GROQ_API_KEY='test-key',
        GROQ_CHAT_MODEL='test-model',
        RAG_CANDIDATE_TOP_K=12,
        RAG_TOP_K=5,
        RAG_MAX_CHUNKS_PER_ITEM=2,
        RAG_RELATIVE_SCORE_DROP=0.12,
        SEMANTIC_MIN_SCORE=0.20,
        AI_TIMEOUT=5,
    )
    @patch('knowledge.services.rag.requests.post')
    @patch('knowledge.services.rag.semantic_search')
    def test_rag_declines_when_gate_rejects_candidates(
        self,
        mock_search,
        mock_post,
    ):
        item = Item.objects.create(
            type=Item.Type.NOTE,
            title='Programação',
            content='Aprenda programação.',
            status=Item.Status.PROCESSED,
        )
        ItemSource.objects.create(item=item, platform='manual', metadata={})
        chunk = Chunk.objects.create(
            item=item,
            kind=Chunk.Kind.CONTENT,
            text='Um site ensina programação.',
            position=0,
            embedding=[1.0, 0.0],
        )
        mock_search.return_value = [SemanticHit(chunk=chunk, score=0.8)]

        gate_response = Mock()
        gate_response.status_code = 200
        gate_response.json.return_value = {
            'choices': [
                {
                    'message': {
                        'content': '{"relevant_sources":[]}'
                    }
                }
            ]
        }
        mock_post.return_value = gate_response

        result = answer_from_library(
            'Como ganhar dinheiro começando com pouco capital?'
        )

        self.assertEqual(result['sources'], [])
        self.assertIn('nenhum trecho responde diretamente', result['answer'])
        self.assertEqual(mock_post.call_count, 1)



class SemanticLibraryRerankTests(TestCase):
    @override_settings(
        GROQ_API_KEY='test-key',
        GROQ_CHAT_MODEL='test-model',
        LIBRARY_SEMANTIC_CANDIDATES=8,
        LIBRARY_SEMANTIC_MAX_RESULTS=8,
        LIBRARY_SEMANTIC_MIN_RELEVANCE=2,
        LIBRARY_SEMANTIC_RELATIVE_DROP=0.10,
        AI_TIMEOUT=5,
    )
    @patch('knowledge.services.semantic.requests.post')
    @patch('knowledge.services.semantic.semantic_search')
    def test_semantic_item_results_reranks_for_relevance(
        self,
        mock_search,
        mock_post,
    ):
        from .services.semantic import semantic_item_results

        relevant_item = Item.objects.create(
            type=Item.Type.NOTE,
            title='Ganhar dinheiro com pouco',
            content='Começar com poucos recursos.',
            status=Item.Status.PROCESSED,
        )
        ItemSource.objects.create(
            item=relevant_item,
            platform='manual',
            metadata={},
        )
        relevant_chunk = Chunk.objects.create(
            item=relevant_item,
            kind=Chunk.Kind.CONTENT,
            text='O conteúdo fala diretamente em ganhar dinheiro começando com pouco.',
            position=0,
            embedding=[1.0, 0.0],
        )

        noisy_item = Item.objects.create(
            type=Item.Type.NOTE,
            title='Marketing',
            content='Siga meu perfil.',
            status=Item.Status.PROCESSED,
        )
        ItemSource.objects.create(
            item=noisy_item,
            platform='manual',
            metadata={},
        )
        noisy_chunk = Chunk.objects.create(
            item=noisy_item,
            kind=Chunk.Kind.CONTENT,
            text='Siga meu perfil para mais dicas de marketing.',
            position=0,
            embedding=[0.9, 0.1],
        )

        mock_search.return_value = [
            SemanticHit(chunk=relevant_chunk, score=0.91),
            SemanticHit(chunk=noisy_chunk, score=0.88),
        ]

        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            'choices': [
                {
                    'message': {
                        'content': (
                            '{"results":['
                            '{"id":1,"relevance":3},'
                            '{"id":2,"relevance":0}'
                            ']}'
                        )
                    }
                }
            ]
        }
        mock_post.return_value = response

        results = semantic_item_results(
            'formas de ganhar dinheiro começando com pouco'
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['item'].pk, relevant_item.pk)
        self.assertEqual(results[0]['relevance'], 3)
