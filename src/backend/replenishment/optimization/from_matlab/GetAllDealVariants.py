from .ThirtyDaysProfit import ThirtyDaysProfit
from .ItemBudget import ItemBudget
from .ValidMOQs import ValidMOQs
from .MinMOQByDeal import MinMOQByDeal
from .DealSumByDeal import DealSumByDeal
from .CopyDeal import CopyDeal
from .GetDealToMOQ import GetDealToMOQ


def GetAllDealVariants(deal):
    deal_keys = list(deal.keys())
    all_moqs = ValidMOQs(deal)

    variants_moqs = []

    for moq in all_moqs:
        deal_copy = CopyDeal(deal)
        GetDealToMOQ(deal_copy, moq)
        DealBudget = sum(ItemBudget(item, moq) for item in deal_copy.values())
        DealEff = sum(ThirtyDaysProfit(item, moq) for item in deal_copy.values())
        dsbd = DealSumByDeal(deal_copy)
        variants_moqs.append({
            "deal": deal_copy,
            "budget": DealBudget,
            "efficiency": DealEff,
            "moq": moq,
            "dsbd": dsbd
        })

    return variants_moqs
