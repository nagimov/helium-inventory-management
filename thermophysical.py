# collection of functions calculating thermophysical properties of helium

p_atm = 101325  # atmospheric pressure [Pa]
T_env = 293  # ambient temperature [K]

R_he = 8.3144598 / 4.003e-3  # J/mol/K / (kg/mol) = J*kg/mol


def d_from_p_sl(p):
    # returns density of saturated helium liquid at given pressure
    assert 90000 < p < 150000
    return -2.115E-04 * p + 1.464E+02


def d_from_p_t(p, T):
    # returns density of helium gas at given pressure and temperature
    assert T > 250  # make sure ideal gas eqn is good enough
    return 1.0 * p / R_he / T


def h_from_p_sl(p):
    # returns enthalpy of saturated helium liquid at given pressure
    assert 90000 < p < 150000
    return 5.651E-02 * p + 4.289E+03


def h_from_p_sv(p):
    # returns enthalpy of saturated helium vapor at given pressure
    assert 90000 < p < 150000
    return -2.515E-07 * p**2 + 4.876E-02 * p + 2.838E+04


def r_from_p_sl(p):
    # returns latent heat of saturated liquid helium at given pressure
    return h_from_p_sv(p) - h_from_p_sl(p)


# some simple testing
assert 124.9 < d_from_p_sl(101325) < 125.0
assert 0.16 < d_from_p_t(101325, 300) < 0.17
assert 10010 < h_from_p_sl(101325) < 10023
assert 30738 < h_from_p_sv(101325) < 30740
