"""Tests for ftl-merge CLI."""

import json
from unittest.mock import patch, MagicMock

import pytest

from ftl_merge.cli import (
    parse_beliefs_from_issue,
    has_outlist,
    load_network,
    retract_beliefs,
    get_issue_for_pr,
)


SAMPLE_NETWORK = {
    "nodes": {
        "propagate-assumes-dependents-exist": {
            "text": "A root defect premise",
            "truth_value": "IN",
            "justifications": [],
            "source": "",
            "source_hash": "",
            "date": "",
            "metadata": {},
        },
        "propagation-is-crash-free": {
            "text": "Propagation completes without errors",
            "truth_value": "OUT",
            "justifications": [
                {
                    "type": "SL",
                    "antecedents": ["propagation-is-bfs"],
                    "outlist": ["propagate-assumes-dependents-exist"],
                    "label": "",
                }
            ],
            "source": "",
            "source_hash": "",
            "date": "",
            "metadata": {},
        },
        "simple-derived": {
            "text": "A derived belief with no outlist",
            "truth_value": "IN",
            "justifications": [
                {
                    "type": "SL",
                    "antecedents": ["propagate-assumes-dependents-exist"],
                    "outlist": [],
                    "label": "",
                }
            ],
            "source": "",
            "source_hash": "",
            "date": "",
            "metadata": {},
        },
    },
    "nogoods": [],
    "repos": {},
}


class TestParseBeliefs:

    def test_extracts_backtick_beliefs(self):
        body = "## Belief\n\n`propagate-assumes-dependents-exist`\n"
        result = parse_beliefs_from_issue(body)
        assert result == ["propagate-assumes-dependents-exist"]

    def test_extracts_multiple(self):
        body = "`belief-one` and `belief-two`"
        result = parse_beliefs_from_issue(body)
        assert result == ["belief-one", "belief-two"]

    def test_filters_non_beliefs(self):
        body = "`src-some-file` `tests-something` `real-belief-id`"
        result = parse_beliefs_from_issue(body)
        assert result == ["real-belief-id"]

    def test_empty_body(self):
        assert parse_beliefs_from_issue("") == []

    def test_no_backticks(self):
        assert parse_beliefs_from_issue("just some text") == []

    def test_single_word_not_matched(self):
        assert parse_beliefs_from_issue("`singleword`") == []

    def test_deduplicates(self):
        body = "`same-belief-id` and `same-belief-id` again"
        result = parse_beliefs_from_issue(body)
        assert result == ["same-belief-id"]


class TestHasOutlist:

    def test_gate_belief_has_outlist(self):
        assert has_outlist("propagation-is-crash-free", SAMPLE_NETWORK) is True

    def test_premise_has_no_outlist(self):
        assert has_outlist("propagate-assumes-dependents-exist", SAMPLE_NETWORK) is False

    def test_derived_with_empty_outlist(self):
        assert has_outlist("simple-derived", SAMPLE_NETWORK) is False

    def test_missing_belief(self):
        assert has_outlist("nonexistent-belief", SAMPLE_NETWORK) is False

    def test_empty_network(self):
        assert has_outlist("anything", {}) is False


class TestLoadNetwork:

    @patch("ftl_merge.cli.subprocess.run")
    def test_returns_parsed_json(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout=json.dumps(SAMPLE_NETWORK)
        )
        result = load_network()
        assert result == SAMPLE_NETWORK

    @patch("ftl_merge.cli.subprocess.run")
    def test_returns_empty_on_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        result = load_network()
        assert result == {}

    @patch("ftl_merge.cli.subprocess.run")
    def test_returns_empty_on_bad_json(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="not json")
        result = load_network()
        assert result == {}

    @patch("ftl_merge.cli.subprocess.run")
    def test_passes_cwd(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout=json.dumps(SAMPLE_NETWORK)
        )
        load_network(cwd="/some/path")
        mock_run.assert_called_once_with(
            "reasons export",
            shell=True, capture_output=True, text=True, cwd="/some/path",
        )


class TestRetractBeliefs:

    @patch("ftl_merge.cli.subprocess.run")
    @patch("ftl_merge.cli.load_network")
    def test_skips_gate_beliefs(self, mock_load, mock_run):
        mock_load.return_value = SAMPLE_NETWORK
        mock_run.return_value = MagicMock(returncode=0)

        retract_beliefs(
            ["propagate-assumes-dependents-exist", "propagation-is-crash-free"],
            pr_number=27,
        )

        calls = [c for c in mock_run.call_args_list]
        retract_cmds = [c[0][0] for c in calls]
        assert any("propagate-assumes-dependents-exist" in cmd for cmd in retract_cmds)
        assert not any("propagation-is-crash-free" in cmd for cmd in retract_cmds)

    @patch("ftl_merge.cli.subprocess.run")
    @patch("ftl_merge.cli.load_network")
    def test_retracts_premises(self, mock_load, mock_run):
        mock_load.return_value = SAMPLE_NETWORK
        mock_run.return_value = MagicMock(returncode=0)

        retract_beliefs(["propagate-assumes-dependents-exist"], pr_number=27)

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "propagate-assumes-dependents-exist" in cmd
        assert 'Fixed in PR #27' in cmd

    @patch("ftl_merge.cli.subprocess.run")
    @patch("ftl_merge.cli.load_network")
    def test_retracts_derived_without_outlist(self, mock_load, mock_run):
        mock_load.return_value = SAMPLE_NETWORK
        mock_run.return_value = MagicMock(returncode=0)

        retract_beliefs(["simple-derived"], pr_number=27)

        mock_run.assert_called_once()
        assert "simple-derived" in mock_run.call_args[0][0]

    @patch("ftl_merge.cli.subprocess.run")
    @patch("ftl_merge.cli.load_network")
    def test_aborts_on_network_load_failure(self, mock_load, mock_run):
        mock_load.return_value = {}

        retract_beliefs(
            ["propagate-assumes-dependents-exist"],
            pr_number=27,
        )

        mock_run.assert_not_called()

    @patch("ftl_merge.cli.subprocess.run")
    @patch("ftl_merge.cli.load_network")
    def test_handles_retract_failure(self, mock_load, mock_run):
        mock_load.return_value = SAMPLE_NETWORK
        mock_run.return_value = MagicMock(returncode=1)

        retract_beliefs(["propagate-assumes-dependents-exist"], pr_number=27)
        mock_run.assert_called_once()

    @patch("ftl_merge.cli.subprocess.run")
    @patch("ftl_merge.cli.load_network")
    def test_passes_cwd_to_retract(self, mock_load, mock_run):
        mock_load.return_value = SAMPLE_NETWORK
        mock_run.return_value = MagicMock(returncode=0)

        retract_beliefs(["propagate-assumes-dependents-exist"], pr_number=27, cwd="/expert")

        mock_load.assert_called_once_with(cwd="/expert")
        assert mock_run.call_args[1]["cwd"] == "/expert"
