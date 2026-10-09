"""Tests for ModelPool VRAM management.

IMPORTANT (dependency classification — GOAL 4): these tests exercise
`hermes_debate`, which is a SEPARATE project (`hermes-debate/` dir, its own
setup.py, package name `hermes_debate`). It is NOT part of this package and is
not installed here. When the package is absent the tests are SKIPPED with a
clear reason (DEPENDENCY FAILURE, not a fake PASS). They RUN for real when
`hermes_debate` is installed. To install: `pip install -e hermes-debate/`
(requires the extra `life_mean_lab[hermes_debate]`).
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

try:
    import hermes_debate  # noqa: F401
    _HAS_HERMES_DEBATE = True
except Exception:  # pragma: no cover - env-dependent
    _HAS_HERMES_DEBATE = False

pytestmark = pytest.mark.skipif(
    not _HAS_HERMES_DEBATE,
    reason="DEPENDENCY FAILURE: separate 'hermes_debate' project not installed "
           "(pip install -e hermes-debate/ to run these)",
)


def _run(coro):
    """Run async coroutine in a sync test."""
    return asyncio.run(coro)


def test_model_pool_start_end_debate():
    """Test pool lifecycle."""
    from hermes_debate.models.model_pool import ModelPool

    mock_manager = AsyncMock()
    pool = ModelPool(manager=mock_manager)

    _run(pool.start_debate())
    assert pool._debate_active is True

    _run(pool.end_debate())
    assert pool._debate_active is False


def test_model_pool_acquire_loads_model():
    """Test that acquire loads model if not loaded."""
    from hermes_debate.models.model_pool import ModelPool

    mock_manager = AsyncMock()
    mock_manager.load_model = AsyncMock(return_value=True)
    mock_manager.get_vram_usage = AsyncMock(return_value={'used_mb': 5000, 'total_mb': 12000})

    pool = ModelPool(manager=mock_manager)
    result = _run(pool.acquire('model_a'))

    assert result is True
    mock_manager.load_model.assert_called_once_with('model_a')


def test_model_pool_acquire_skips_if_loaded():
    """Test that acquire doesn't reload if already loaded."""
    from hermes_debate.models.model_pool import ModelPool

    mock_manager = AsyncMock()
    mock_manager.load_model = AsyncMock(return_value=True)
    mock_manager.get_vram_usage = AsyncMock(return_value={'used_mb': 5000})

    pool = ModelPool(manager=mock_manager)

    # First acquire loads the model
    _run(pool.acquire('model_a'))
    load_call_count = mock_manager.load_model.call_count

    # Second acquire should not trigger another load
    _run(pool.acquire('model_a'))
    assert mock_manager.load_model.call_count == load_call_count


def test_model_pool_release_unloads_when_refs_zero():
    """Test that release unloads model when ref count reaches zero."""
    from hermes_debate.models.model_pool import ModelPool

    mock_manager = AsyncMock()
    mock_manager.load_model = AsyncMock(return_value=True)
    mock_manager.get_vram_usage = AsyncMock(return_value={'used_mb': 5000})
    mock_manager.unload_model = AsyncMock(return_value=True)

    pool = ModelPool(manager=mock_manager)

    _run(pool.acquire('model_a'))
    _run(pool.release('model_a'))

    mock_manager.unload_model.assert_called_once_with('model_a')


def test_model_pool_release_keeps_if_refs_remain():
    """Test that release doesn't unload if other refs exist."""
    from hermes_debate.models.model_pool import ModelPool

    mock_manager = AsyncMock()
    mock_manager.load_model = AsyncMock(return_value=True)
    mock_manager.get_vram_usage = AsyncMock(return_value={'used_mb': 5000})
    mock_manager.unload_model = AsyncMock(return_value=True)

    pool = ModelPool(manager=mock_manager)

    # Acquire twice (simulating two contexts)
    _run(pool.acquire('model_a'))
    _run(pool.acquire('model_a'))

    # Release once - should not unload
    _run(pool.release('model_a'))
    mock_manager.unload_model.assert_not_called()

    # Release second time - should unload
    _run(pool.release('model_a'))
    mock_manager.unload_model.assert_called_once_with('model_a')


def test_model_pool_ensure_all_loaded():
    """Test pre-loading multiple models."""
    from hermes_debate.models.model_pool import ModelPool

    mock_manager = AsyncMock()
    mock_manager.load_model = AsyncMock(return_value=True)
    mock_manager.get_vram_usage = AsyncMock(return_value={'used_mb': 5000})

    pool = ModelPool(manager=mock_manager)

    loaded = _run(pool.ensure_all_loaded(['model_a', 'model_b']))

    assert len(loaded) == 2
    assert 'model_a' in loaded
    assert 'model_b' in loaded
    assert mock_manager.load_model.call_count == 2


def test_model_pool_cleanup():
    """Test cleanup unloads all models."""
    from hermes_debate.models.model_pool import ModelPool

    mock_manager = AsyncMock()
    mock_manager.load_model = AsyncMock(return_value=True)
    mock_manager.get_vram_usage = AsyncMock(return_value={'used_mb': 5000})
    mock_manager.unload_model = AsyncMock(return_value=True)

    pool = ModelPool(manager=mock_manager)

    _run(pool.acquire('model_a'))
    _run(pool.acquire('model_b'))
    _run(pool.cleanup())

    assert mock_manager.unload_model.call_count == 2
    assert len(pool._slots) == 0


def test_model_pool_get_status():
    """Test status reporting."""
    from hermes_debate.models.model_pool import ModelPool

    mock_manager = AsyncMock()
    mock_manager.load_model = AsyncMock(return_value=True)
    mock_manager.get_vram_usage = AsyncMock(return_value={'used_mb': 5000})

    pool = ModelPool(manager=mock_manager)

    _run(pool.acquire('model_a'))
    status = pool.get_status()

    assert status['loaded_count'] == 1
    assert 'model_a' in status['loaded_models']


def test_model_pool_context_manager():
    """Test async context manager."""
    from hermes_debate.models.model_pool import ModelPool

    mock_manager = AsyncMock()
    pool = ModelPool(manager=mock_manager)

    async def run():
        async with pool:
            assert pool._debate_active is True
        assert pool._debate_active is False

    _run(run())


def test_model_pool_active_models_property():
    """Test active_models property."""
    from hermes_debate.models.model_pool import ModelPool

    mock_manager = AsyncMock()
    mock_manager.load_model = AsyncMock(return_value=True)
    mock_manager.get_vram_usage = AsyncMock(return_value={'used_mb': 5000})

    pool = ModelPool(manager=mock_manager)

    _run(pool.acquire('model_a'))
    _run(pool.acquire('model_b'))

    active = pool.active_models
    assert 'model_a' in active
    assert 'model_b' in active
