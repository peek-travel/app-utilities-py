from peek_app_utilities.internal.peek.custom_questions.custom_question_service import (
    CustomQuestionService,
)
from peek_app_utilities.models.peek.custom_question import CustomQuestion, CustomQuestionOption

ALL_QUESTIONS = [
    {
        "id": "cq_anq67",
        "questionType": "CHECK_BOX",
        "text": "Check box - Per Guest - Adult Only",
        "answerDefaultValue": None,
        "hint": None,
        "internalLabel": None,
        "perGuest": True,
    },
    {
        "id": "cq_bq48e",
        "questionType": "SELECT_ONE",
        "text": "Multiple Choice",
        "answerDefaultValue": None,
        "hint": None,
        "internalLabel": None,
        "perGuest": False,
        "options": [
            {"id": "cqao_mwdgvw", "text": "Option A", "order": 1},
            {"id": "cqao_va78v7", "text": "Option B", "order": 2},
        ],
    },
]


async def test_fetches_the_account_wide_questions_and_maps_them(gql):
    gql.queue({"questions": ALL_QUESTIONS})

    questions = await CustomQuestionService(gql).get_all()

    assert questions == [
        CustomQuestion(
            id="cq_anq67",
            order=0,
            is_required=False,
            question_text="Check box - Per Guest - Adult Only",
            hint_text=None,
            question_type="CHECK_BOX",
            internal_label=None,
            per_guest=True,
            default_value=None,
            options=[],
        ),
        CustomQuestion(
            id="cq_bq48e",
            order=0,
            is_required=False,
            question_text="Multiple Choice",
            hint_text=None,
            question_type="SELECT_ONE",
            internal_label=None,
            per_guest=False,
            default_value=None,
            options=[
                CustomQuestionOption(id="cqao_mwdgvw", order=1, value="Option A"),
                CustomQuestionOption(id="cqao_va78v7", order=2, value="Option B"),
            ],
        ),
    ]
    assert len(gql.calls) == 1
    call = gql.calls[0]
    assert call.endpoint_name == "sales"
    assert "questions" in call.query
    assert "ChoiceQuestion" in call.query
    assert call.variables == {}


async def test_returns_an_empty_list_when_a_200_response_carries_no_data(gql):
    gql.queue_body({})
    assert await CustomQuestionService(gql).get_all() == []


async def test_returns_an_empty_list_when_the_account_has_no_questions(gql):
    gql.queue({"questions": []})
    assert await CustomQuestionService(gql).get_all() == []
