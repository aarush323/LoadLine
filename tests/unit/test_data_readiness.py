from loadline.core.data_readiness import DatasetMeasurement, ReadOperation, evaluate_data_readiness


def test_not_measured_does_not_claim_data_missing():
    result = evaluate_data_readiness(
        [ReadOperation(id="a", needs_harvested_ids=True)],
        DatasetMeasurement(size=None, source="postgres"),
    )
    assert result.blocker_code is None
    assert result.measured is False


def test_zero_rows_all_need_ids_is_data_missing():
    result = evaluate_data_readiness(
        [
            ReadOperation(id="by_id", needs_harvested_ids=True),
            ReadOperation(id="detail", needs_harvested_ids=True),
        ],
        DatasetMeasurement(size=0, source="postgres"),
    )
    assert result.blocker_code == "data_missing"
    assert result.working_operations == ()
