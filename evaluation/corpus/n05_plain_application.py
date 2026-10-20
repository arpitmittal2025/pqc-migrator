"""Ordinary business logic with no cryptography of any kind."""

from dataclasses import dataclass


@dataclass
class Invoice:
    number: str
    amount: float

    def with_tax(self, rate):
        return self.amount * (1 + rate)


def total(invoices):
    return sum(invoice.amount for invoice in invoices)
