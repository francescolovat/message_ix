import pytest
import numpy as np
from numpy import testing as npt
import pandas.util.testing as pdt

from ixmp import Platform
from message_ix import Scenario

from message_ix.testing import (
    make_dantzig,
    models,
    TS_DF,
    TS_DF_CLEARED,
    TS_DF_SHIFT
)


def test_run_clone(tmpdir):
    # this test is designed to cover the full functionality of the GAMS API
    # - initialize a new ixmp platform instance
    # - create a new scenario based on Dantzigs tutorial transport model
    # - solve the model and read back the solution from the output
    # - perform tests on the objective value and the timeseries data
    mp = Platform(tmpdir, dbtype='HSQLDB')
    scen = make_dantzig(mp, solve=True)
    assert np.isclose(scen.var('OBJ')['lvl'], 153.675)
    pdt.assert_frame_equal(scen.timeseries(iamc=True), TS_DF)

    # cloning with `keep_solution=True` keeps all timeseries and the solution
    # (same behaviour as `ixmp.Scenario`)
    scen2 = scen.clone(keep_solution=True)
    assert np.isclose(scen2.var('OBJ')['lvl'], 153.675)
    pdt.assert_frame_equal(scen2.timeseries(iamc=True), TS_DF)

    # cloning with `keep_solution=False` drops the solution and only keeps
    # timeseries set as `meta=True` or prior to the first model year
    # (DIFFERENT behaviour from `ixmp.Scenario`)
    scen3 = scen.clone(keep_solution=False)
    assert np.isnan(scen3.var('OBJ')['lvl'])
    pdt.assert_frame_equal(scen3.timeseries(iamc=True), TS_DF_CLEARED)


def test_run_remove_solution(test_mp):
    # create a new instance of the transport problem and solve it
    scen = make_dantzig(test_mp, solve=True)
    assert np.isclose(scen.var('OBJ')['lvl'], 153.675)

    # check that re-solving the model will raise an error if a solution exists
    pytest.raises(ValueError, scen.solve)

    # check that removing solution with a first-model-year arg raises an error
    # (DIFFERENT behaviour from `ixmp.Scenario`)
    pytest.raises(TypeError, scen.remove_solution, first_model_year=1964)

    # check that removing solution does not delete timeseries data
    # before first model year (DIFFERENT behaviour from `ixmp.Scenario`)
    scen.remove_solution()
    pdt.assert_frame_equal(scen.timeseries(iamc=True), TS_DF_CLEARED)


def test_shift_first_model_year(test_mp):
    scen = make_dantzig(test_mp, solve=True, multi_year=True)
    clone = scen.clone(shift_first_model_year=1964)

    # check that solution and timeseries in new model horizon have been removed
    assert np.isnan(clone.var('OBJ')['lvl'])
    pdt.assert_frame_equal(clone.timeseries(iamc=True), TS_DF_SHIFT)
    # check that the variable `ACT` is now the parameter `historical_activity`
    assert not clone.par('historical_activity').empty


def scenario_list(mp):
    return mp.scenario_list(default=False)[['model', 'scenario']]


def assert_multi_db(mp1, mp2):
    pdt.assert_frame_equal(scenario_list(mp1), scenario_list(mp2))


def test_multi_db_run(tmpdir):
    # create a new instance of the transport problem and solve it
    mp1 = Platform(tmpdir / 'mp1', dbtype='HSQLDB')
    scen1 = make_dantzig(mp1, solve=True)

    mp2 = Platform(tmpdir / 'mp2', dbtype='HSQLDB')
    # add other unit to make sure that the mapping is correct during clone
    mp2.add_unit('wrong_unit')
    mp2.add_region('wrong_region', 'country')

    # check that cloning across platforms must copy the full solution
    dest = dict(platform=mp2)
    pytest.raises(ValueError, scen1.clone, **dest, keep_solution=False)
    pytest.raises(ValueError, scen1.clone, **dest, shift_first_model_year=1964)

    # clone solved model across platforms (with default settings)
    scen1.clone(platform=mp2, keep_solution=True)

    mp2.close_db()
    del mp2

    _mp2 = Platform(tmpdir / 'mp2', dbtype='HSQLDB')
    info = models['dantzig']
    scen2 = Scenario(_mp2, info['model'], info['scenario'])
    assert_multi_db(mp1, _mp2)

    # check that sets, variables and parameter were copied correctly
    npt.assert_array_equal(scen1.set('node'), scen2.set('node'))
    pdt.assert_frame_equal(scen1.par('var_cost'), scen2.par('var_cost'))
    assert np.isclose(scen2.var('OBJ')['lvl'], 153.675)
    pdt.assert_frame_equal(scen1.var('ACT'), scen2.var('ACT'))

    # check that custom unit, region and timeseries are migrated correctly
    pdt.assert_frame_equal(scen2.timeseries(iamc=True), TS_DF)