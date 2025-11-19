from django import forms
from django.utils import timezone
from dateutil.relativedelta import relativedelta


class ForecastDateRangeForm(forms.Form):
    """Форма для вибору діапазону даних для прогнозу."""
    
    # За замовчуванням беремо дані за останні 90 днів
    default_start = (timezone.now() - relativedelta(days=90)).date()
    default_end = timezone.now().date()

    start_date = forms.DateField(
        label="Початкова дата історії",
        initial=default_start,
        widget=forms.DateInput(attrs={'type': 'date'}),
        help_text="Дата, з якої починаємо брати історичні дані продажів."
    )
    
    end_date = forms.DateField(
        label="Кінцева дата історії",
        initial=default_end,
        widget=forms.DateInput(attrs={'type': 'date'}),
        help_text="Дата, по яку включно беремо історичні дані."
    )

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')

        if start_date and end_date and start_date >= end_date:
            raise forms.ValidationError("Початкова дата має бути раніше кінцевої.")
        
        return cleaned_data
