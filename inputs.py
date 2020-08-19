from datetime import datetime
import numpy as np
from pytz import timezone
from thermophysical import p_atm, \
    T_env, \
    d_from_p_t, \
    d_from_p_sl, \
    h_from_p_sl, \
    h_from_p_sv, \
    r_from_p_sl

# liquefier data
v_linde_dewar_L_hr = 54.4  # production rate [L/hr]
p_linde_dewar_gauge_psi = 3.2  # pressure in the dewar [psi gauge]
p_linde_dewar = 101325 + p_linde_dewar_gauge_psi * 6894.76  # pressure in the dewar [Pa]
t_rampup_linde_cold = 1 * 3600  # time required to ramp linde production from cold state [s]
t_rampup_linde_warm = 3 * 3600  # time required to ramp linde production from warm state [s]
t_linde_warmup_threshold = 2 * 24 * 3600  # max off time after which full warmup needed
t_linde_warmup = 2 * 24 * 3600  # full warmup time, in addition to the threshold
V_linde_dewar_min_safe_L = 100  # minimal safe level in the dewar (stop fills when drops below) [L]
V_linde_dewar_min_okay_L = 110  # minimal level in the dewar at which fills can be started [L]
V_linde_dewar_max_L = 900  # maximal level in the dewar [L]
V_linde_dewar_start_L = 500  # threshold of dewar level for NOT starting linde if it's not running already [L]
x_linde_dewar_loss_day = 0.5 / 100  # dewar liquid helium loss per day
x_linde_production_transfer = 47.0 / 100  # max reduction of production at max withdrawal rate
x_linde_dewar_fill_loss = 0.0 / 100  # losses when filling dewars as a fraction of what lands into dewar
v_dewar_pull_run_L_hr = 79.2  # max dewar withdrawal rate while linde is running [L/hr]
v_dewar_pull_off_L_hr = 120  # max dewar withdrawal rate rate while linde is off [L/hr]
m_linde_loss_g_s = 0.01  # rate of helium loss when liquefier is running [g/s]
# liquefier calcs
d_linde_dewar = d_from_p_sl(p_linde_dewar)  # density of liquid in the dewar [kg/m^3]
m_linde_dewar = v_linde_dewar_L_hr * 1e-3 / 3600 * d_linde_dewar  # production rate [kg/s]
M_linde_dewar_min_safe = V_linde_dewar_min_safe_L * 1e-3 * d_linde_dewar  # min amount in the dewar [kg]
M_linde_dewar_min_okay = V_linde_dewar_min_okay_L * 1e-3 * d_linde_dewar  # min amount in the dewar [kg]
M_linde_dewar_max = V_linde_dewar_max_L * 1e-3 * d_linde_dewar  # max amount in the dewar [kg]
# M_linde_dewar_start: threshold of dewar level for NOT starting linde if it's not running [kg]
M_linde_dewar_start = V_linde_dewar_start_L * 1e-3 * d_linde_dewar
m_linde_dewar_loss = M_linde_dewar_max * x_linde_dewar_loss_day / 24 / 3600  # dewar evap rate [kg/s]
m_dewar_pull_run = v_dewar_pull_run_L_hr * 1e-3 * d_linde_dewar / 3600  # max dewar fill flow rate [L/hr]
m_dewar_pull_off = v_dewar_pull_off_L_hr * 1e-3 * d_linde_dewar / 3600  # dewar fill flow rate [L/hr]
m_dewar_pull_loss_run = x_linde_dewar_fill_loss * m_dewar_pull_run  # dewar fill losses while linde is running [kg/s]
m_dewar_fill_loss_off = x_linde_dewar_fill_loss * m_dewar_pull_off  # dewar fill losses while linde is off [kg/s]
m_linde_loss = m_linde_loss_g_s * 1e-3  # rate of helium loss when liquefier is running [kg/s]

# hp & lp storage data
p_hp_storage_max_psi = 3600  # max allowed pressure in hp storage [psi]
p_hp_storage_min_psi = 500  # min allowed pressure in hp storage [psi]
m_hp_compressor = 4.08e-3 / 3  # total flow of recovery compressors per each compressor [kg/s]
V_hp_storage_cu_ft = 45.9 * 9  # total volume of impure hp storage [ft^3]
V_bag_max_cu_ft = 1500  # max volume of the bag [ft^3]
x_bag_setpoint_high_1 = 0.70  # high setpoint of bag volume for hp compressor 1
x_bag_setpoint_high_2 = 0.75  # high setpoint of bag volume for hp compressor 2
x_bag_setpoint_high_3 = 0.80  # high setpoint of bag volume for hp compressor 3
x_bag_setpoint_low_1 = 0.25  # low setpoint of bag volume for hp compressor 1
x_bag_setpoint_low_2 = 0.30  # low setpoint of bag volume for hp compressor 2
x_bag_setpoint_low_3 = 0.35  # low setpoint of bag volume for hp compressor 3
# hp & lp storage calcs
p_hp_storage_max = p_hp_storage_max_psi * 6894.76  # max allowed pressure in hp storage [Pa]
p_hp_storage_min = p_hp_storage_min_psi * 6894.76  # min allowed pressure in hp storage [Pa]
V_hp_storage = V_hp_storage_cu_ft * 0.0283168  # total volume of impure hp storage [m^3]
V_bag_max = V_bag_max_cu_ft * 0.0283168  # max volume of the bag [m^3]
M_hp_storage_max = V_hp_storage * d_from_p_t(p_hp_storage_max, T_env)  # max amount of gas in hp storage [kg]
M_hp_storage_min = V_hp_storage * d_from_p_t(p_hp_storage_min, T_env)  # min amount of gas in hp storage [kg]
d_bag = d_from_p_t(p_atm, T_env)  # density of helium in helium bag [kg/m^3]
M_bag_max = V_bag_max * d_bag  # max amount of gas in the bag [kg]

# portable dewars data
N_dewars_purchased_max = 100  # max number of dewars to be purchased
N_dewars = 9  # total number of dewars
p_portable_dewar = 101325  # pressure in portable dewars [Pa]
x_portable_dewar_loss_day = 1.0 / 100  # liquid helium loss per day [-]
V_portable_dewar_full_L = 330  # max level [L]
V_portable_dewar_min_L = 20  # min level [L]
V_portable_dewar_topup_L = 150  # threshold for top up [L]
V_portable_dewar_cooldown_L = 100  # amount of helium required to cool down dewar from warm state [L]
# portable dewars calcs
d_portable_dewar = d_from_p_sl(p_portable_dewar)  # density of liquid in portable dewars [kg/m^3]
M_portable_dewar_full = V_portable_dewar_full_L * 1e-3 * d_portable_dewar  # full amount in portable dewars [kg]
M_portable_dewar_min = V_portable_dewar_min_L * 1e-3 * d_portable_dewar  # full amount in portable dewars [kg]
M_portable_dewar_topup = V_portable_dewar_topup_L * 1e-3 * d_portable_dewar  # threshold for top up [kg]
# m_portable_dewar_loss: loss rate from portable dewars [kg/s]
m_portable_dewar_loss = x_portable_dewar_loss_day * M_portable_dewar_full / 24 / 3600
# M_portable_dewar_cooldown: amount of helium required to cool down dewar from warm state [kg]
M_portable_dewar_cooldown = V_portable_dewar_cooldown_L * 1e-3 * d_portable_dewar  # cool down amount [kg]
# M_linde_dewar_fill_ok: minimal required level in main dewar to start a fill
M_linde_dewar_fill_ok = M_linde_dewar_min_safe + M_portable_dewar_topup

# ucn source cryostat data
v_ucn_static_L_hr = 12  # flow rate from only static heat load (4K + 1K pots) [L/hr]
v_ucn_beam_L_hr = 19  # flow rate from only beam loading (4K + 1K pots), adjusted to make the run possible [L/hr]
v_transfer_line_L_hr = 79.2  # flow rate through the transfer line as seen from linde dewar [L/hr]
P_transfer_line = 0.06 * 40  # heat load to the transfer line [W/m * m = W]
P_transfer_misc = 0.5 + 1  # heat load from valves, field joints, etc. [W]
p_ucn_4K = 101325  # pressure in the 4K pot of ucn source
V_ucn_4K_min_L = 100  # min level in UCN cryostat [L]
V_ucn_4K_max_L = 180  # max level in UCN cryostat [L]
v_ucn_cooldown_L_hr = 19.0  # flow rate during cooldown loads [L/hr]
t_ucn_cooldown_hrs = 72  # ucn cryostat cooldown period [hr]
# ucn source cryostat calcs
d_ucn_4K = d_from_p_sl(p_ucn_4K)  # density of liquid in ucn 4K pot [kg/m^3]
M_ucn_4K_min = V_ucn_4K_min_L * 1e-3 * d_ucn_4K  # min level in UCN cryostat [kg]
M_ucn_4K_max = V_ucn_4K_max_L * 1e-3 * d_ucn_4K  # max level in UCN cryostat [kg]
m_ucn_static = v_ucn_static_L_hr * 1e-3 * d_ucn_4K / 3600  # flow rate at static heat load (4K + 1K pots) [kg/s]
m_ucn_beam = v_ucn_beam_L_hr * 1e-3 * d_ucn_4K / 3600  # flow rate at heat load with beam (4K + 1K pots) [kg/s]
m_ucn_cooldown = v_ucn_cooldown_L_hr * 1e-3 * d_ucn_4K / 3600  # flow rate at cooldown loads [kg/s]
# m_transfer_line: flow rate through the transfer line as seen from linde dewar [kg/s]
m_transfer_line = v_transfer_line_L_hr * 1e-3 * d_linde_dewar / 3600
P_transfer_total = P_transfer_line + P_transfer_misc  # total heat load to transfer line [W]
# enthalpy balance: h(p_linde_dewar, SL) = h(p_ucn_4K, SV) * x_vapor_ucn_4K + h(p_ucn_4K, SL) * (1 - x_vapor_ucn_4K)
# x_vapor_ucn_4K_JT: fraction of helium vapor generated from JT process in transfer line
x_vapor_ucn_4K_JT = (h_from_p_sl(p_linde_dewar) - h_from_p_sl(p_ucn_4K))/(h_from_p_sv(p_ucn_4K) - h_from_p_sl(p_ucn_4K))
# q_latent_transfer_line: latent heat of liquid helium in transfer line [J/kg]
q_latent_transfer_line = 0.5 * (r_from_p_sl(p_linde_dewar) + r_from_p_sl(p_ucn_4K))  # when in doubt, use average
m_vapor_ucn_4K_Q = P_transfer_total / q_latent_transfer_line  # helium vapor generated by heat load [kg/s]
m_transfer_line_trickle = m_vapor_ucn_4K_Q + x_vapor_ucn_4K_JT * m_transfer_line  # minimal flow to keep transfer line cold [kg/s]
t_ucn_cooldown = t_ucn_cooldown_hrs * 3600  # ucn cryostat cooldown period [s]

# timezone and conversions
triumf_tz = timezone('America/Vancouver')
parse_time = lambda x: triumf_tz.localize(datetime.strptime(x, '%Y-%m-%d %H:%M:%S')).timestamp()

# iteration data
timestep = 60  # timestep for iteration [s]
start_time = parse_time('2027-04-01 00:00:00')  # starting time in YYYY-MM-DD HH:MM:SS format
end_time = parse_time('2027-12-31 23:59:59')  # end time in YYYY-MM-DD HH:MM:SS format
prediction_window = 5 * 24 * 3600  # period for predicting future use and making operational decisions [s]

# schedule tuples: [(start, stop), (start, stop), ... ]
# dewar 1 is 0, dewar 2 is 1, etc.
schedule = {}
# make sure beam doesn't start for at least t_ucn_cooldown period after ucn starts running
schedule['ucn_source'] = [(parse_time('2027-04-01 08:00:00'), parse_time('2027-05-01 20:00:00')),
                          (parse_time('2027-06-01 08:00:00'), parse_time('2027-07-01 20:00:00')),
                          (parse_time('2027-08-01 08:00:00'), parse_time('2027-09-01 20:00:00')),]
schedule['ucn_beam'] = [(parse_time('2027-04-14 08:00:00'), parse_time('2027-04-30 20:00:00')),
                        (parse_time('2027-06-14 08:00:00'), parse_time('2027-06-30 20:00:00')),
                        (parse_time('2027-08-14 08:00:00'), parse_time('2027-08-30 20:00:00')),]
schedule[0] = [(parse_time('2027-04-08 08:00:00'), parse_time('2027-08-22 20:00:00'))]
schedule[1] = [(parse_time('2027-08-26 08:00:00'), parse_time('2027-09-27 20:00:00'))]
schedule[2] = schedule[1]  # 2 and 3 operate together
schedule[3] = [(parse_time('2027-10-14 08:00:00'), parse_time('2027-11-22 20:00:00'))]
schedule[4] = schedule[3]  # 4 and 5 operate together
schedule[5] = [(parse_time('2027-04-09 08:00:00'), parse_time('2027-09-17 20:00:00'))]
schedule[6] = [(parse_time('2027-06-25 08:00:00'), parse_time('2027-12-13 20:00:00'))]
schedule[7] = [(parse_time('2027-04-13 08:00:00'), parse_time('2027-12-01 20:00:00'))]
schedule[8] = [(parse_time('2027-04-13 08:00:00'), parse_time('2027-12-15 20:00:00'))]
schedule[9] = [(parse_time('2027-04-18 08:00:00'), parse_time('2027-05-10 20:00:00'))]
schedule[10] = [(parse_time('2027-04-19 08:00:00'), parse_time('2027-07-26 20:00:00'))]
schedule[11] = [(parse_time('2027-04-19 08:00:00'), parse_time('2027-07-19 20:00:00'))]

# consumption data:     L/wk                      to kg/s
cmms_consumption = np.zeros(12, dtype=float)
cmms_consumption[0] = 420 * 1e-3 * d_portable_dewar / 7 / 24 / 3600
cmms_consumption[1] = 154 * 1e-3 * d_portable_dewar / 7 / 24 / 3600
cmms_consumption[2] = 330 * 1e-3 * d_portable_dewar / 7 / 24 / 3600
cmms_consumption[3] = 140 * 1e-3 * d_portable_dewar / 7 / 24 / 3600
cmms_consumption[4] = 495 * 1e-3 * d_portable_dewar / 7 / 24 / 3600
cmms_consumption[5] = 330 * 1e-3 * d_portable_dewar / 7 / 24 / 3600
cmms_consumption[6] = 330 * 1e-3 * d_portable_dewar / 7 / 24 / 3600
cmms_consumption[7] = 140 * 1e-3 * d_portable_dewar / 7 / 24 / 3600
cmms_consumption[8] = 330 * 1e-3 * d_portable_dewar / 7 / 24 / 3600
cmms_consumption[9] = 33.3 * 1e-3 * d_portable_dewar / 7 / 24 / 3600
cmms_consumption[10] = 330 * 1e-3 * d_portable_dewar / 7 / 24 / 3600
cmms_consumption[11] = 165 * 1e-3 * d_portable_dewar / 7 / 24 / 3600
