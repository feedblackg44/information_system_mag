from decimal import Decimal
from django import forms
from django.utils import timezone
from dateutil.relativedelta import relativedelta
from crm.models import Warehouse


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


class GenerateReplenishmentForm(forms.Form):
    warehouse = forms.ModelChoiceField(
        queryset=Warehouse.objects.all(),
        label="Склад поповнення",
        empty_label=None
    )
    global_coverage_days = forms.IntegerField(
        label="Цільове покриття (днів)",
        initial=14,
        min_value=1
    )
    global_credit_terms = forms.IntegerField(
        label="Кредитні умови (днів)",
        initial=45,
        min_value=0
    )

class AlgorithmInputForm(forms.Form):
    """Форма для збору фінальних параметрів перед запуском алгоритму."""
    
    max_investment_period = forms.IntegerField(
        label="Макс. період інвестицій (днів)",
        min_value=1,
        help_text="Максимальна кількість днів, на яку дозволено заморожувати кошти у закупівлі."
    )
    
class FinalBudgetForm(forms.Form):
    # Це буде просто поле для введення, діапазон перевіримо в Admin View
    final_budget = forms.DecimalField(
        label="Фінальний бюджет закупівлі (у.о.)",
        min_value=Decimal('0.01'),
        help_text="Введіть суму, яку ви готові витратити."
    )
