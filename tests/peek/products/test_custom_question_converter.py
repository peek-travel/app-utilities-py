from peek_app_utilities.internal.peek.products.custom_question_converter import (
    from_question_configurations,
)
from peek_app_utilities.internal.peek.products.custom_question_queries import (
    QuestionConfigurationNode,
)
from peek_app_utilities.models.peek.custom_question import CustomQuestion, CustomQuestionOption


def test_maps_a_free_text_question_pulling_order_is_required_from_the_config():
    configs: list[QuestionConfigurationNode] = [
        {
            "isRequired": True,
            "order": 2,
            "question": {
                "id": "cq_gw5xn",
                "questionType": "TEXT",
                "text": "Text Input",
                "answerDefaultValue": None,
                "hint": "this is a hint text",
                "internalLabel": None,
                "perGuest": False,
            },
        }
    ]

    assert from_question_configurations(configs) == [
        CustomQuestion(
            id="cq_gw5xn",
            order=2,
            is_required=True,
            question_text="Text Input",
            hint_text="this is a hint text",
            question_type="TEXT",
            internal_label=None,
            per_guest=False,
            default_value=None,
            options=[],
        )
    ]


def test_maps_a_choice_questions_options_into_id_order_value():
    configs: list[QuestionConfigurationNode] = [
        {
            "isRequired": False,
            "order": 3,
            "question": {
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
        }
    ]

    question = from_question_configurations(configs)[0]
    assert question.question_type == "SELECT_ONE"
    assert question.options == [
        CustomQuestionOption(id="cqao_mwdgvw", order=1, value="Option A"),
        CustomQuestionOption(id="cqao_va78v7", order=2, value="Option B"),
    ]


def test_defaults_missing_config_question_fields_to_safe_values():
    configs: list[QuestionConfigurationNode] = [
        {"question": {"id": "cq_x", "questionType": "CHECK_BOX", "text": "Check box"}}
    ]

    assert from_question_configurations(configs) == [
        CustomQuestion(
            id="cq_x",
            order=0,
            is_required=False,
            question_text="Check box",
            hint_text=None,
            question_type="CHECK_BOX",
            internal_label=None,
            per_guest=False,
            default_value=None,
            options=[],
        )
    ]


def test_returns_an_empty_list_for_no_configurations():
    assert from_question_configurations([]) == []
