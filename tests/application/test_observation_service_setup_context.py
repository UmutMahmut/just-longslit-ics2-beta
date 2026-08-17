from justls.ics.application.services.observation_service import ObservationService
from justls.ics.application.services.setup_context_service import SetupContextService
from justls.ics.kernel.runtime import RuntimeAssembler
from justls.ics.domain.setup import SessionDataContext


class RecordingDispatcher:
    def __init__(self) -> None:
        self.request = None

    def dispatch(self, request):
        self.request = request
        return None


def test_observation_service_attaches_setup_context_to_arm_request() -> None:
    dispatcher = RecordingDispatcher()
    setup_service = SetupContextService(
        SessionDataContext(
            observers="Observer",
            project_id="P-001",
            pi_name="PI",
            support_operator="Support",
            root_name="science",
            date_prefix="20260527",
            comment="night setup",
            next_frame_index=5,
            data_directory="/data/just",
        )
    )
    service = ObservationService(
        runtime=RuntimeAssembler().build(),
        dispatcher=dispatcher,
        setup_context_service=setup_service,
    )

    service.arm(
        exp_time_s=30.0,
        frame_type="science",
        operator_note="note",
        save_requested=True,
    )

    assert dispatcher.request is not None
    params = dispatcher.request.params

    assert params["setup_context"] == {
        "observers": "Observer",
        "project_id": "P-001",
        "pi_name": "PI",
        "support_operator": "Support",
        "root_name": "science",
        "date_prefix": "20260527",
        "comment": "night setup",
        "next_frame_index": 5,
        "data_directory": "/data/just",
    }
    assert params["data_preview"] == {
        "next_frame_token": "20260527-0005",
        "file_stem": "science_20260527_0005",
        "fits_filename": "science_20260527_0005.fits",
        "data_directory": "/data/just",
    }
    assert setup_service.get_context().next_frame_index == 6
