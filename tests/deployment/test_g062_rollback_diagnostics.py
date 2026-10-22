"""Keep failed rollback evidence even when later identities match."""
from test_coordinated_release_state_machine import run_scenario


def test_restored_identity_does_not_erase_static_verification_failure():
    report = run_scenario('''
$VerifyStatic = { [ordered]@{ success = $false; detail = 'candidate static failed' } }
$RollbackStatic = { param($baseline)
    $script:currentStaticSha = $baseline.static_sha
    [ordered]@{ success = $false; detail = 'public static verification missing' }
}
''')
    assert report['success'] is False
    assert report['final_state_domain'] == 'BASELINE_BASELINE'
    assert report['stop_reason'] == 'baseline_not_confirmed_after_rollback'
    entry = report['recovery_log'][-1]
    assert entry['static_rollback_result']['success'] is False
    assert entry['static_rollback_result']['detail'] == 'public static verification missing'
    assert entry['app_rollback_result']['success'] is True


def test_terminal_recovery_also_preserves_failure_evidence():
    report = run_scenario('''
$VerifyStatic = { [ordered]@{ success = $false; requires_source_change = $true } }
$RollbackStatic = { param($baseline)
    [ordered]@{ success = $false; detail = 'rollback transport failure' }
}
''')
    assert report['success'] is False
    assert report['final_state_domain'] == 'MIXED_OR_UNVERIFIED'
    assert report['recovery_log'][-1]['static_rollback_result']['detail'] == 'rollback transport failure'
