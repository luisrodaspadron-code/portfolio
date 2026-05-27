from app.services.backtest_service import walk_forward_splits


def test_walk_forward_splits_trade_after_signal_window():
    splits = walk_forward_splits(total_days=130, lookback_days=60, rebalance_every=21)

    assert splits
    first = splits[0]
    assert first["train_start_index"] == 0
    assert first["train_end_index"] == 60
    assert first["rebalance_index"] == 61
    assert all(split["train_end_index"] < split["rebalance_index"] for split in splits)

