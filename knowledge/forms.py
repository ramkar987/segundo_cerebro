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
        widget=forms.TextInput(attrs={'placeholder': 'Título opcional para notas manuais'}),
    )
