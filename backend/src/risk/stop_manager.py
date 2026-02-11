"""
ATR-based stop-loss, take-profit, and trailing stop calculations.
"""


class StopManager:
    """Calculates stop-loss, take-profit, and trailing stop levels using ATR."""

    @staticmethod
    def calculate_stop_loss(
        direction: str,
        entry_price: float,
        atr: float,
        multiplier: float = 2.0,
    ) -> float:
        """
        Calculate ATR-based stop-loss level.

        Args:
            direction: "BUY" or "SELL"
            entry_price: Entry price
            atr: Current ATR value
            multiplier: ATR multiplier (1.5-2.0 intraday, 2.0-2.5 swing, 2.5-3.5 position)

        Returns:
            Stop-loss price level
        """
        stop_distance = atr * multiplier
        if direction == "BUY":
            return entry_price - stop_distance
        return entry_price + stop_distance

    @staticmethod
    def calculate_take_profit(
        direction: str,
        entry_price: float,
        atr: float,
        multiplier: float = 2.0,
        risk_reward: float = 2.0,
    ) -> float:
        """
        Calculate ATR-based take-profit level.

        Args:
            direction: "BUY" or "SELL"
            entry_price: Entry price
            atr: Current ATR value
            multiplier: ATR multiplier for stop distance
            risk_reward: Risk-reward ratio (TP distance = SL distance * risk_reward)

        Returns:
            Take-profit price level
        """
        tp_distance = atr * multiplier * risk_reward
        if direction == "BUY":
            return entry_price + tp_distance
        return entry_price - tp_distance

    @staticmethod
    def calculate_trailing_stop(
        direction: str,
        current_price: float,
        atr: float,
        multiplier: float = 2.0,
    ) -> float:
        """
        Calculate trailing stop level based on current price and ATR.

        Args:
            direction: "BUY" or "SELL"
            current_price: Current market price
            atr: Current ATR value
            multiplier: ATR multiplier

        Returns:
            Trailing stop price level
        """
        trail_distance = atr * multiplier
        if direction == "BUY":
            return current_price - trail_distance
        return current_price + trail_distance
