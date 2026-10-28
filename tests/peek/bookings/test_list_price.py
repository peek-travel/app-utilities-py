from decimal import Decimal
from typing import cast

import pytest

from peek_app_utilities.internal.peek.bookings.list_price import distribute_list_price


class TestDistributeListPrice:
    def test_gives_the_remainder_cent_to_the_last_ticket_10_over_3(self):
        assert distribute_list_price("10.00", 3) == ["3.33", "3.33", "3.34"]

    def test_splits_evenly_when_the_total_divides_exactly(self):
        assert distribute_list_price("9.00", 3) == ["3.00", "3.00", "3.00"]
        assert distribute_list_price("1,000", 4) == ["250.00", "250.00", "250.00", "250.00"]

    def test_gives_the_whole_amount_to_a_single_ticket(self):
        assert distribute_list_price("100", 1) == ["100.00"]
        assert distribute_list_price("10.00", 1) == ["10.00"]

    def test_parses_integers_decimals_and_comma_thousands_separators(self):
        assert distribute_list_price("100", 1) == ["100.00"]
        assert distribute_list_price("1,234.56", 2) == ["617.28", "617.28"]
        assert distribute_list_price("1,000.50", 2) == ["500.25", "500.25"]

    def test_always_sums_back_to_the_exact_total(self):
        amounts = distribute_list_price("100.00", 7)
        assert sum(int(Decimal(a) * 100) for a in amounts) == 10000
        assert len(amounts) == 7

    @pytest.mark.parametrize("bad", ["", "   ", "abc", "-5", "0", "0.00", "1,00,0abc", "$10"])
    def test_raises_on_non_positive_or_non_numeric_amounts(self, bad: str):
        with pytest.raises(ValueError, match="listPrice must be a positive number"):
            distribute_list_price(bad, 2)

    def test_raises_on_a_non_string_amount(self):
        with pytest.raises(ValueError, match="listPrice must be a positive number"):
            distribute_list_price(cast("str", None), 2)
