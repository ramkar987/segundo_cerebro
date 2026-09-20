import re

from django import forms


class CaptureForm(forms.Form):
    capture = forms.CharField(
        label='',
        widget=forms.Textarea(attrs={
            'rows': 4,
            'placeholder': 'Cole um link do Instagram/YouTube, uma página web ou escreva uma nota…',
            'autofocus': True,
        }),
    )
    title = forms.CharField(
        label='Título opcional',
        required=False,
        max_length=300,
        widget=forms.TextInput(
            attrs={'placeholder': 'Título opcional para notas manuais'}
        ),
    )


class BatchCaptureForm(forms.Form):
    batch_capture = forms.CharField(
        label='',
        widget=forms.Textarea(attrs={
            'rows': 10,
            'placeholder': (
                'Cole vários links, um por linha…\n'
                'https://exemplo.com/artigo\n'
                'https://www.instagram.com/p/...\n'
                'https://youtu.be/...'
            ),
        }),
    )

    def clean_batch_capture(self):
        value = self.cleaned_data['batch_capture']
        lines = []

        for raw_line in value.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            # Facilita colar listas com marcadores ou numeração.
            line = re.sub(r'^(?:[-*•]\s+|\d+[.)]\s+)', '', line).strip()
            if line:
                lines.append(line)

        if not lines:
            raise forms.ValidationError('Cole pelo menos um link.')

        if len(lines) > 100:
            raise forms.ValidationError(
                'O limite é de 100 links por lote. Divida em dois lotes.'
            )

        return lines



class AskLibraryForm(forms.Form):
    question = forms.CharField(
        label='',
        max_length=2000,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': (
                'Pergunte algo sobre o que você já guardou… '
                'Ex.: O que eu salvei sobre formas de ganhar dinheiro com tecnologia?'
            ),
            'autofocus': True,
        }),
    )
