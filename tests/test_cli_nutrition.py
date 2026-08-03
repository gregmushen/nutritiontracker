from unittest.mock import patch

import httpx
from click.testing import CliRunner

from app.cli.client import APIClient
from app.cli.main import cli
from app.cli.nutrition import POUNDS_PER_KILOGRAM

runner = CliRunner()


def test_cli_exposes_nutrition_commands():
    result = runner.invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "activity" in result.output
    assert "foods" in result.output
    assert "diary" in result.output
    assert "events" in result.output
    assert "journal" in result.output
    assert "kitchen" in result.output
    assert "query" in result.output
    assert "recipes" in result.output
    assert "request" in result.output
    assert "stats" in result.output
    assert "users" in result.output
    assert "weight" in result.output


def test_food_search_calls_api_and_formats_results():
    food = {
        "id": 12,
        "name": "Chicken breast",
        "brand": None,
        "source": "usda_foundation",
        "calories_kcal": 165,
        "protein_g": 31,
        "carbs_g": 0,
        "fat_g": 3.6,
    }
    with patch("app.cli.client.APIClient.request", return_value=[food]) as request:
        result = runner.invoke(cli, ["foods", "search", "chicken"])

    assert result.exit_code == 0
    assert "[12] Chicken breast" in result.output
    assert "165 kcal | P 31g C 0g F 3.6g" in result.output
    request.assert_called_once_with(
        "GET",
        "/foods/search",
        params={"q": "chicken", "source": "all", "limit": 10, "offset": 0},
    )


def test_json_option_emits_machine_readable_output():
    with patch(
        "app.cli.client.APIClient.request",
        return_value={"status": "ok", "version": "0.1.0"},
    ):
        result = runner.invoke(cli, ["--json", "health"])

    assert result.exit_code == 0
    assert '"status": "ok"' in result.output


def test_api_client_sends_bearer_token():
    response = httpx.Response(
        200,
        json={"status": "ok"},
        request=httpx.Request("GET", "https://example.test/health"),
    )
    with patch("app.cli.client.httpx.request", return_value=response) as request:
        APIClient("https://example.test", "secret").request("GET", "/health")

    assert request.call_args.kwargs["headers"] == {"Authorization": "Bearer secret"}


def test_api_errors_are_reported_without_traceback():
    response = httpx.Response(
        401,
        json={"detail": "Invalid bearer token"},
        request=httpx.Request("GET", "https://example.test/health"),
    )
    with patch("app.cli.client.httpx.request", return_value=response):
        result = runner.invoke(cli, ["health"])

    assert result.exit_code == 1
    assert "API request failed (401): Invalid bearer token" in result.output
    assert "Traceback" not in result.output


def test_diary_add_posts_entry():
    entry = {
        "food_name": "Chicken breast",
        "amount": 100,
        "unit": "g",
        "nutrients_total": {
            "calories_kcal": 165,
            "protein_g": 31,
            "carbs_g": 0,
            "fat_g": 3.6,
        },
    }
    with patch("app.cli.client.APIClient.request", return_value=entry) as request:
        result = runner.invoke(
            cli,
            [
                "diary",
                "add",
                "12",
                "100",
                "g",
                "--meal",
                "lunch",
                "--date",
                "2026-08-02",
            ],
        )

    assert result.exit_code == 0
    assert "Logged Chicken breast to lunch" in result.output
    request.assert_called_once_with(
        "POST",
        "/diary/2026-08-02/entries",
        json={
            "food_id": 12,
            "amount": 100.0,
            "unit": "g",
            "meal_type": "lunch",
        },
    )


def test_diary_search_queries_food_history():
    entry = {
        "id": 4,
        "date": "2026-08-01",
        "meal_type": "lunch",
        "food_name": "Chicken breast",
        "amount": 100,
        "unit": "g",
        "nutrients_total": {
            "calories_kcal": 165,
            "protein_g": 31,
            "carbs_g": 0,
            "fat_g": 3.6,
        },
    }
    with patch("app.cli.client.APIClient.request", return_value=[entry]) as request:
        result = runner.invoke(cli, ["diary", "search", "chicken"])

    assert result.exit_code == 0
    assert "2026-08-01 lunch: Chicken breast" in result.output
    request.assert_called_once_with("GET", "/diary/search", params={"q": "chicken"})


def test_query_supports_repeated_parameters_and_outputs_json():
    with patch(
        "app.cli.client.APIClient.request",
        return_value=[{"id": 1, "name": "oats"}],
    ) as request:
        result = runner.invoke(
            cli,
            [
                "query",
                "/kitchen/inventory",
                "--param",
                "q=oats",
                "--param",
                "status=have",
            ],
        )

    assert result.exit_code == 0
    assert '"name": "oats"' in result.output
    request.assert_called_once_with(
        "GET",
        "/kitchen/inventory",
        params=[("q", "oats"), ("status", "have")],
    )


def test_query_rejects_embedded_query_string():
    with patch("app.cli.client.APIClient.request") as request:
        result = runner.invoke(cli, ["query", "/events?limit=10"])

    assert result.exit_code == 2
    assert "use --param KEY=VALUE" in result.output
    request.assert_not_called()


def test_request_supports_mutating_api_endpoints():
    with patch(
        "app.cli.client.APIClient.request",
        return_value={"id": 7, "name": "Dinner"},
    ) as request:
        result = runner.invoke(
            cli,
            [
                "request",
                "PATCH",
                "/recipes/7",
                "--param",
                "audit=true",
                "--data",
                '{"name":"Dinner"}',
            ],
        )

    assert result.exit_code == 0
    assert '"name": "Dinner"' in result.output
    request.assert_called_once_with(
        "PATCH",
        "/recipes/7",
        params=[("audit", "true")],
        json={"name": "Dinner"},
    )


def test_request_reads_json_body_from_file():
    with runner.isolated_filesystem():
        with open("event.json", "w") as payload:
            payload.write('{"event_type_id":2,"date":"2026-08-02"}')
        with patch(
            "app.cli.client.APIClient.request",
            return_value={"id": 9},
        ) as request:
            result = runner.invoke(
                cli,
                [
                    "request",
                    "POST",
                    "/events",
                    "--data-file",
                    "event.json",
                ],
            )

    assert result.exit_code == 0
    request.assert_called_once_with(
        "POST",
        "/events",
        params=[],
        json={"event_type_id": 2, "date": "2026-08-02"},
    )


def test_request_rejects_non_object_json():
    with patch("app.cli.client.APIClient.request") as request:
        result = runner.invoke(
            cli,
            ["request", "POST", "/events", "--data", "[]"],
        )

    assert result.exit_code == 2
    assert "must contain a JSON object" in result.output
    request.assert_not_called()


def test_food_create_posts_json():
    body = {"name": "My oats", "source": "custom"}
    with patch(
        "app.cli.client.APIClient.request",
        return_value={"id": 3, **body},
    ) as request:
        result = runner.invoke(
            cli,
            ["foods", "create", "--data", '{"name":"My oats","source":"custom"}'],
        )

    assert result.exit_code == 0
    request.assert_called_once_with("POST", "/foods", json=body)


def test_diary_update_patches_selected_fields():
    with patch(
        "app.cli.client.APIClient.request",
        return_value={"id": 5},
    ) as request:
        result = runner.invoke(
            cli,
            ["diary", "update", "5", "--amount", "2", "--meal", "dinner"],
        )

    assert result.exit_code == 0
    request.assert_called_once_with(
        "PATCH",
        "/diary/entries/5",
        json={"amount": 2.0, "meal_type": "dinner"},
    )


def test_activity_import_posts_complete_observation():
    with patch(
        "app.cli.client.APIClient.request",
        return_value={"date": "2026-08-02", "steps": 1200},
    ) as request:
        result = runner.invoke(
            cli,
            [
                "activity",
                "import-steps",
                "--source",
                "apple_health",
                "--observed-at",
                "2026-08-02T12:00:00-07:00",
                "--period-start",
                "2026-08-02T00:00:00-07:00",
                "--period-end",
                "2026-08-02T12:00:00-07:00",
                "--steps",
                "1200",
                "--timezone",
                "America/Los_Angeles",
            ],
        )

    assert result.exit_code == 0
    request.assert_called_once_with(
        "POST",
        "/imports/activity/steps",
        json={
            "source": "apple_health",
            "observed_at": "2026-08-02T12:00:00-07:00",
            "period_start": "2026-08-02T00:00:00-07:00",
            "period_end": "2026-08-02T12:00:00-07:00",
            "steps_total_today": 1200,
            "timezone": "America/Los_Angeles",
        },
    )


def test_journal_add_posts_scores_and_tags():
    with patch(
        "app.cli.client.APIClient.request",
        return_value={"id": 4},
    ) as request:
        result = runner.invoke(
            cli,
            [
                "journal",
                "add",
                "Good day",
                "--date",
                "2026-08-02",
                "--tag",
                "training",
                "--mood",
                "8",
            ],
        )

    assert result.exit_code == 0
    request.assert_called_once_with(
        "POST",
        "/journal",
        json={
            "date": "2026-08-02",
            "body": "Good day",
            "tags": ["training"],
            "mood_score": 8,
        },
    )


def test_event_add_preserves_zero_value():
    with patch(
        "app.cli.client.APIClient.request",
        return_value={"id": 6},
    ) as request:
        result = runner.invoke(
            cli,
            [
                "events",
                "add",
                "2",
                "--date",
                "2026-08-02",
                "--value",
                "0",
                "--unit",
                "minutes",
            ],
        )

    assert result.exit_code == 0
    request.assert_called_once_with(
        "POST",
        "/events",
        json={
            "event_type_id": 2,
            "date": "2026-08-02",
            "value": 0.0,
            "unit": "minutes",
        },
    )


def test_kitchen_inventory_search_maps_filters():
    with patch(
        "app.cli.client.APIClient.request",
        return_value=[],
    ) as request:
        result = runner.invoke(
            cli,
            [
                "kitchen",
                "inventory",
                "list",
                "--search",
                "oats",
                "--status",
                "have",
            ],
        )

    assert result.exit_code == 0
    request.assert_called_once_with(
        "GET",
        "/kitchen/inventory",
        params={"status": "have", "q": "oats"},
    )


def test_shopping_generate_posts_meal_ids():
    with patch(
        "app.cli.client.APIClient.request",
        return_value=[],
    ) as request:
        result = runner.invoke(
            cli,
            ["kitchen", "shopping", "generate", "3", "8"],
        )

    assert result.exit_code == 0
    request.assert_called_once_with(
        "POST",
        "/kitchen/shopping-list/generate",
        json={"meal_ids": [3, 8]},
    )


def test_user_create_posts_name():
    with patch(
        "app.cli.client.APIClient.request",
        return_value={"id": 2, "name": "Alex", "token": "new-token"},
    ) as request:
        result = runner.invoke(cli, ["users", "create", "Alex"])

    assert result.exit_code == 0
    request.assert_called_once_with("POST", "/users", json={"name": "Alex"})


def test_stats_rejects_reversed_range_without_api_call():
    with patch("app.cli.client.APIClient.request") as request:
        result = runner.invoke(cli, ["stats", "range", "2026-08-03", "2026-08-02"])

    assert result.exit_code == 2
    assert "START must not be after END" in result.output
    request.assert_not_called()


def test_weight_add_converts_pounds_to_kilograms():
    response = {"id": 7, "date": "2026-08-02", "weight_kg": 81.6466}
    with patch("app.cli.client.APIClient.request", return_value=response) as request:
        result = runner.invoke(
            cli,
            [
                "weight",
                "add",
                "180",
                "--unit",
                "lb",
                "--date",
                "2026-08-02",
            ],
        )

    assert result.exit_code == 0
    body = request.call_args.kwargs["json"]
    assert body["weight_kg"] == 180 / POUNDS_PER_KILOGRAM
    assert "81.6 kg" in result.output


def test_weight_list_requires_both_range_bounds():
    with patch("app.cli.client.APIClient.request") as request:
        result = runner.invoke(cli, ["weight", "list", "--start", "2026-08-01"])

    assert result.exit_code == 2
    assert "--start and --end must be used together" in result.output
    request.assert_not_called()
