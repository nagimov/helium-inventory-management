#!/usr/bin/env python3

import hashlib
import sys
import time
import numpy as np
import matplotlib.pyplot as plt
import thermophysical
import inputs
from ctypes import c_int32  # little hack to create a "mutable integer"

# create data array storing system's state and its history
dt = inputs.timestep
total_steps = int((inputs.end_time - inputs.start_time) / dt) + 1
dewars_list = range(inputs.N_dewars)
purchased_dewars_list = range(inputs.N_dewars_purchased_max)
dewars_purchased = c_int32(0)
total_cmms = len(inputs.cmms_consumption)
cmms_list = range(total_cmms)
charts = {}

timestamps = np.arange(inputs.start_time, inputs.end_time, dt)
timestamps_days = np.arange(0, (inputs.end_time-inputs.start_time)/24/3600, dt/24/3600)

linde_storage = np.zeros(total_steps,
    dtype={'names': ['hp',  'bag', 'dewar', 'ucn', 'loss'],
         'formats': [float, float, float,   float, float]}
)
linde_state = np.zeros(total_steps,
    dtype={'names': ['run', 'warmup', 'hp_comp_1', 'hp_comp_2', 'hp_comp_3', 'transfer', 'transfer_trickle', 'filling'],
         'formats': [bool,  bool,     bool,        bool,        bool,        bool,       bool,               bool]}
)
linde_state_logbook = {}

dewar_storage = np.zeros((inputs.N_dewars, total_steps), dtype=float)
dewar_cooldown = np.zeros(inputs.N_dewars, dtype=float)
dewar_state = np.zeros((inputs.N_dewars, total_steps),
    dtype={'names': ['warm', 'store', 'low', 'fill', 'cmms'],
         'formats': [bool,   bool,    bool,  bool,   bool]}
)
dewar_state_logbook = {}

purchased_dewar_storage = np.zeros((inputs.N_dewars_purchased_max, total_steps), dtype=float)
purchased_dewar_state_logbook = {}

# cmms_states indicates if cmms is off (-1) or number of the dewar feeding it minus one
# numbers higher then 100 indicate a purchased dewar, e.g. 100 - first purchased dewar. 101 - second purchased dewar
cmms_state = np.zeros((total_cmms, total_steps), dtype=int)
cmms_state_logbook = []

ucn_state = np.zeros(total_steps,
    dtype={'names': ['static', 'beam'],
         'formats': [bool,     bool]})
ucn_state_logbook = {}


def change_dewar_state(dewar, new_state, step):
    # changes the state of specified dewar and marks it as "low" if it's below the threshold level
    if dewar < 100:
        for ds in dewar_state.dtype.names:
            dewar_state[ds][dewar][step] = False
        if new_state == 'store' and dewar_storage[dewar][step] < inputs.M_portable_dewar_topup:
            new_state = 'low'
        # when dewar becomes "warm", amount of LHe required for cooldown is set
        if new_state == 'warm':
            dewar_cooldown[dewar] = -inputs.M_portable_dewar_cooldown
        dewar_state[new_state][dewar][step] = True


def log_linde_state(step):
    # logs which linde states changed and when
    for s in linde_state.dtype.names:
        if linde_state[s][step] and not linde_state[s][step-1]:
            linde_state_logbook[f'{s}_1'] = step
            print(f'linde state change: "{s}" from 0 to 1')
        elif not linde_state[s][step] and linde_state[s][step-1]:
            linde_state_logbook[f'{s}_0'] = step
            print(f'linde state change: "{s}" from 1 to 0')


def log_dewar_state(step):
    # logs which dewar states changed and when
    for d in dewars_list:
        for s in dewar_state.dtype.names:
            if dewar_state[s][d][step] and not dewar_state[s][d][step-1]:
                dewar_state_logbook[f'{d}_{s}_1'] = step
                print(f'dewar {d} state change: "{s}" from 0 to 1')
            elif not dewar_state[s][d][step] and dewar_state[s][d][step-1]:
                dewar_state_logbook[f'{d}_{s}_0'] = step
                print(f'dewar {d} state change: "{s}" from 1 to 0')


def log_ucn_state(step):
    # logs which ucn states changed and when
    for s in ucn_state.dtype.names:
        if ucn_state[s][step] and not ucn_state[s][step-1]:
            ucn_state_logbook[f'{s}_1'] = step
            print(f'ucn state change: "{s}" from 0 to 1')
        elif not ucn_state[s][step] and ucn_state[s][step-1]:
            ucn_state_logbook[f'{s}_0'] = step
            print(f'ucn state change: "{s}" from 1 to 0')


def log_cmms_state(step):
    # logs which cmms states changed and when
    for c in cmms_list:
        if cmms_state[c][step] != cmms_state[c][step-1]:
            state_from = cmms_state[c][step-1]
            state_to = cmms_state[c][step]
            cmms_state_logbook.append((state_from, state_to, step))
            if state_from == -1:
                state_from = '"no dewar"'
            if state_to == -1:
                state_to = '"no dewar"'
            print(f'cmms {c} state change: from dewar {state_from} to dewar {state_to}')


def calc_dewar_fill(step, d):
    # returns amount landed into the portable dewar and losses to the bag considering dewar's warm/cold state
    if not dewar_state['fill'][d][step]:
        quit_iteration(step, 'dewar thinks it is being filled while linde disagrees')
    # define how much is being pushed from main dewar
    if linde_state['run'][step]:
        transfer_to_dewar = inputs.m_dewar_fill_run
        losses_to_bag = inputs.m_dewar_fill_loss_run
    else:
        transfer_to_dewar = inputs.m_dewar_fill_off
        losses_to_bag = inputs.m_dewar_fill_loss_off
    # if cooldown amount wasn't delivered, dewar is still "warm"
    if dewar_cooldown[d] < 0:
        print(d, dewar_cooldown[d])
        dewar_cooldown[d] += transfer_to_dewar * dt
        return 0, transfer_to_dewar + losses_to_bag
    else:
        return transfer_to_dewar, losses_to_bag


def calc_ucn_load(step):
    # returns static heat load of ucn cryostat considering cooldown mode
    assert ucn_state['static'][step]  # make sure ucn is at static heat load
    started = ucn_state_logbook['static_1']
    since_start = timestamps[step] - timestamps[started]
    load_mult = 1.0
    if since_start < inputs.t_ucn_cooldown:  # if in cooldown mode
        if ucn_state['beam'][step]:  # if trying to run beam while in cooldown mode
            quit_iteration(step, 'trying to run beam to ucn in cooldown mode')
        load_mult = inputs.x_ucn_cooldown
    return load_mult * inputs.m_ucn_static


def calc_linde_production(step):
    # calculates linde production considering both initial ramp up and reduced production during transfers
    assert linde_state['run'][step]  # make sure linde is running
    t_rampup = inputs.t_rampup_linde_cold
    if 'run_0' not in linde_state_logbook:     # if never stopped before then running first time (wow logic!)
        t_rampup = inputs.t_rampup_linde_warm  # i.e. cooling down from warm state
    elif 'warmup_0' in linde_state_logbook:                                      # if was warmed up before
        if linde_state_logbook['run_1'] - linde_state_logbook['warmup_0'] == 1:  # if started after warmup
            t_rampup = inputs.t_rampup_linde_warm                                # then cooling down from warm
    started = linde_state_logbook['run_1']
    since_start = timestamps[step] - timestamps[started]
    ramp_mult = min(since_start / t_rampup, 1.0)
    # adjust production during transfers
    transfer_mult = 1.0
    if linde_state['transfer'][step]:
        transfer_mult = 1.0 - inputs.x_linde_production_transfer
    return inputs.m_linde_dewar * ramp_mult * transfer_mult


def op_linde(step):
    # liquefaction
    if linde_state['run'][step]:
        production = calc_linde_production(step)
        linde_storage['hp'][step] -= (production + inputs.m_linde_loss) * dt
        linde_storage['dewar'][step] += production * dt
        linde_storage['loss'][step] += inputs.m_linde_loss * dt
    # evaporation from main dewar when linde is off
    else:
        dewar_loss = min(linde_storage['dewar'][step], inputs.m_linde_dewar_loss * dt)  # cannot loose more than have
        linde_storage['dewar'][step] -= dewar_loss
        linde_storage['bag'][step] += dewar_loss
    # filling portable dewar
    if linde_state['filling'][step]:
        filling_dewar_num = -1
        for d in dewars_list:
            if dewar_state['fill'][d][step]:
                filling_dewar_num = d
                break
        if filling_dewar_num == -1:
            quit_iteration(step, 'linde thinks it is filling the dewar but all dewars disagree')
        to_portable_dewar, to_bag = calc_dewar_fill(step, filling_dewar_num)
        dewar_storage[filling_dewar_num][step] += to_portable_dewar * dt
        linde_storage['bag'][step] += to_bag * dt
        linde_storage['dewar'][step] -= (to_portable_dewar + to_bag) * dt
    # filling ucn cryostat
    if linde_state['transfer'][step]:
        linde_storage['dewar'][step] -= (inputs.m_transfer_line + inputs.m_transfer_line_loss) * dt
        linde_storage['bag'][step] += inputs.m_transfer_line_loss * dt
        linde_storage['ucn'][step] += inputs.m_transfer_line * dt
    if linde_state['transfer_trickle'][step]:
        linde_storage['dewar'][step] -= inputs.m_transfer_line_trickle * dt
        linde_storage['bag'][step] += inputs.m_transfer_line_trickle * dt
    # venting from the bag if it's too full and recording the losses
    if linde_storage['bag'][step] > inputs.M_bag_max:
        linde_storage['loss'][step] += linde_storage['bag'][step] - inputs.M_bag_max
        linde_storage['bag'][step] = inputs.M_bag_max


def op_hp_compressors(step):
    # compression from bag to hp
    hp_throughput = inputs.m_hp_compressor * dt
    hp_transfer = min(linde_storage['bag'][step], hp_throughput)  # can't transfer more than left in the bag
    if linde_state['hp_comp_1'][step]:
        linde_storage['bag'][step] -= hp_transfer
        linde_storage['hp'][step] += hp_transfer
    hp_transfer = min(linde_storage['bag'][step], hp_throughput)
    if linde_state['hp_comp_2'][step]:
        linde_storage['bag'][step] -= hp_transfer
        linde_storage['hp'][step] += hp_transfer
    hp_transfer = min(linde_storage['bag'][step], hp_throughput)
    if linde_state['hp_comp_3'][step]:
        linde_storage['bag'][step] -= hp_transfer
        linde_storage['hp'][step] += hp_transfer


def op_ucn(step):
    # evaporation from heat loads
    if ucn_state['static'][step]:
        ucn_flow = calc_ucn_load(step) * dt
        linde_storage['ucn'][step] -= ucn_flow
        linde_storage['bag'][step] += ucn_flow
    if ucn_state['beam'][step]:
        ucn_flow = inputs.m_ucn_beam * dt
        linde_storage['ucn'][step] -= ucn_flow
        linde_storage['bag'][step] += ucn_flow


def op_dewars(step):
    for d in dewars_list:
        # evaporation from dewars "on the wall"
        if dewar_state[d][step]['store'] or dewar_state[d][step]['low']:
            dewar_storage[d][step] -= inputs.m_portable_dewar_loss * dt
            linde_storage['bag'][step] += inputs.m_portable_dewar_loss * dt
        # dewars feeding cmms experiments are processed by op_cmms, including purchased ones
        if dewar_state[d][step]['cmms']:
            pass
        # dewars being filled from main dewar are processed by op_linde
        if dewar_state[d][step]['fill']:
            pass
        # warm dewars stay warm and very empty
        if dewar_state[d][step]['warm']:
            dewar_storage[d][step] = 0.0


def op_cmms(step):
    # evaporation from dewars feeding cmms, including purchased ones
    for c in cmms_list:
        cmms_dewar = cmms_state[c][step]
        if cmms_dewar != -1:  # if cmms c is running during step
            cmms_evap = inputs.cmms_consumption[c] * dt
            linde_storage['bag'][step] += cmms_evap
            # triumf dewars
            if cmms_dewar < 100:
                dewar_storage[cmms_dewar][step] -= cmms_evap
            # purchased dewars
            else:
                purchased_dewar_storage[cmms_dewar-100][step] -= cmms_evap


def initialize():  # init the world
    # distribute helium within linde storage volumes
    linde_storage['hp'][0] = 3.8 * thermophysical.d_from_p_sl(130000)
    linde_storage['dewar'][0] = 0.05 * thermophysical.d_from_p_sl(130000)
    linde_storage['bag'][0] = 0.0
    linde_storage['ucn'][0] = 0.0
    linde_storage['loss'][0] = 0.0
    # turn off all cmms experiments
    for cmms in cmms_list:
        cmms_state[cmms][0] = -1
    # set linde, dewars and ucn states (redundant since np.zeros does that so just to be explicit)
    for s in linde_state.dtype.names:
        linde_state[s][0] = False
    # empty dewars and warm them up
    for d in dewars_list:
        dewar_storage[d][0] = 0
        change_dewar_state(d, 'warm', 0)
    # ucn states
    for s in ucn_state.dtype.names:
        ucn_state[s][0] = False


def carry_amounts(step):
    # carry helium amounts from previous steps so they could be adjusted via -= and +=
    for k in linde_storage.dtype.names:
        linde_storage[k][step] = linde_storage[k][step-1]
    for d in dewars_list:
        dewar_storage[d][step] = dewar_storage[d][step-1]
    for d in purchased_dewars_list:
        purchased_dewar_storage[d][step] = purchased_dewar_storage[d][step-1]


def carry_states(step):
    # carry states from previous steps
    for d in dewars_list:
        dewar_state[d][step] = dewar_state[d][step-1]
    for cmms in cmms_list:
        cmms_state[cmms][step] = cmms_state[cmms][step-1]
    for k in linde_state.dtype.names:
        linde_state[k][step] = linde_state[k][step-1]


def is_this_thing_on(step, thing):
    # lurks through the schedule and tells if the thing is on
    t = timestamps[step]
    for s in inputs.schedule[thing]:
        if s[0] <= t <= s[1]:
            return True
    return False


# state setter function cannot use current state of the world - they suppose to set it
# make sure to use only [step-1] for decision making in order to avoid cycling the logic
def set_ucn_states(step):
    ucn_state['static'][step] = is_this_thing_on(step, 'ucn_source')
    ucn_state['beam'][step] = is_this_thing_on(step, 'ucn_beam')


def purchase_dewar(step):
    # adjusts total number of purchased dewars, "fills up" one purchased dewar and returns its number
    if dewars_purchased.value >= inputs.N_dewars_purchased_max:
        quit_iteration(step, 'stop buying dewars already')
    purchased_dewar_storage[dewars_purchased.value][step] = inputs.M_portable_dewar_full
    dewars_purchased.value += 1
    return 100+dewars_purchased.value-1


def set_cmms_states(step):
    dewars_needed = []
    for cmms in cmms_list:
        if is_this_thing_on(step, cmms):  # cmms runs according to schedule
            need_dewar = True
            # if dewar already connected, check its level
            dewar_connected = cmms_state[cmms][step-1]
            if dewar_connected != -1:
                # triumf dewar
                if dewar_connected < 100:
                    if dewar_storage[dewar_connected][step-1] > inputs.M_portable_dewar_min:
                        need_dewar = False
                # purchased dewar
                else:
                    if purchased_dewar_storage[dewar_connected-100][step-1] > inputs.M_portable_dewar_min:
                        need_dewar = False
            if need_dewar:
                dewars_needed.append(cmms)
        else:  # cmms doesn't run according to schedule
            cmms_state[cmms][step] = -1
            # if dewar is attached, return it
            dewar_connected = cmms_state[cmms][step-1]
            if dewar_connected != -1:
                change_dewar_state(dewar_connected, 'store', step)
    if len(dewars_needed) > 0:
        # find available dewars from storage
        ready_dewars = find_ready_dewars_now(step-1)
        dewars_available = len(ready_dewars)
        # if not enough dewars available, purchase some
        for _ in range(len(dewars_needed) - dewars_available):
            ready_dewars.append(purchase_dewar(step))
        for cmms, dewar in zip(dewars_needed, ready_dewars):
            # if cmms had dewar connected, return it
            dewar_connected = cmms_state[cmms][step-1]
            if dewar_connected != -1:
                change_dewar_state(dewar_connected, 'store', step)
            # attach new dewar
            cmms_state[cmms][step] = dewar
            change_dewar_state(dewar, 'cmms', step)


def find_ready_dewars_now(step):
    # returns list of dewars ready for grabs right now sorted by levels from high to low
    d_num = []
    d_lvl = []
    for d in dewars_list:
        if dewar_state['store'][d][step]:
            d_lvl.append(dewar_storage[d][step])
            d_num.append(d)
    return [k for _, k in sorted(zip(d_lvl, d_num), reverse=True)]


def find_ready_dewars_future(step, period):
    # returns list of dewars that will be ready for grabs in specified period sorted by levels from high to low
    projected_level_loss = period * inputs.m_portable_dewar_loss
    d_num = []
    d_lvl = []
    for d in dewars_list:
        if dewar_state['store'][d][step]:
            if dewar_storage[d][step] > projected_level_loss + inputs.M_portable_dewar_topup:
                d_lvl.append(dewar_storage[d][step])
                d_num.append(d)
    return [k for _, k in sorted(zip(d_lvl, d_num), reverse=True)]


def next_dewar_to_fill_now(step):
    # returns list of dewar that can be filled right now sorted by levels from high to low
    d_num = []
    d_lvl = []
    for d in dewars_list:
        if dewar_state['low'][d][step] or dewar_state['warm'][d][step]:
            d_lvl.append(dewar_storage[d][step])
            d_num.append(d)
    return [k for _, k in sorted(zip(d_lvl, d_num), reverse=True)]


def next_dewar_to_fill_future(step, period):
    # returns list of dewars that can be filled for future readiness within specified period sorted from high to low
    projected_level_loss = period * inputs.m_portable_dewar_loss
    d_num = []
    d_lvl = []
    for d in dewars_list:
        if dewar_state['low'][d][step] or dewar_state['warm'][d][step]:
            d_lvl.append(dewar_storage[d][step])
            d_num.append(d)
        if dewar_state['store'][d][step]:
            if dewar_storage[d][step] < projected_level_loss + inputs.M_portable_dewar_topup:
                d_lvl.append(dewar_storage[d][step])
                d_num.append(d)
    return [k for _, k in sorted(zip(d_lvl, d_num), reverse=True)]


def who_needs_dewars(step, period):
    # returns cmms experiments that will require dewars within specified period
    # TODO: cmms might require more than one dewar, e.g. during cooldown
    out = []
    t = timestamps[step]
    for c in cmms_list:
        cmms_dewar = cmms_state[c][step]
        # if experiment will start running within period, it'll need a dewar
        if cmms_dewar == -1:  # if cmms c is not running during step
            for s in inputs.schedule[c]:
                if t <= s[0] <= t + period:  # if cmms will start operating within period
                    out.append((c, s[0]))
        # if experiment is running and will run out of LHe within period, it'll need a dewar
        else:  # if cmms c is running during step
            # triumf dewar
            if cmms_dewar < 100:
                time_left = (dewar_storage[cmms_dewar][step] - inputs.M_portable_dewar_min) / inputs.cmms_consumption[c]
            else:
            # purchased dewar
                time_left = (purchased_dewar_storage[cmms_dewar-100][step] -
                             inputs.M_portable_dewar_min) / inputs.cmms_consumption[c]
            if time_left <= period:
                out.append((c, t + dt * int(time_left / dt)))
    return out


def we_need_more_dewars(step, period):  # not enough mana
    # defines whether there is lack of ready dewars
    # how many cmms experiments will need dewars in 3 days
    cmms_expects_dewars = len(who_needs_dewars(step, period))
    # how many dewars in storage will be ready in 3 days
    dewars_will_be_ready = len(find_ready_dewars_future(step, period))
    if dewars_will_be_ready < cmms_expects_dewars:
        return True
    return False


def set_dewar_states(step):
    for d in dewars_list:
        # if dewar on the wall falls below threshold, it needs a topup
        if dewar_state['store'][d][step-1]:
            if dewar_storage[d][step-1] <= inputs.M_portable_dewar_topup:
                change_dewar_state(d, 'low', step)
        # if dewar goes to 0, it warms up
        if dewar_storage[d][step-1] < 0:
            # only if it isn't being filled already, since cooldown is a fill at zero level
            # if fill was interrupted during cooldown, cooldown will need to start again
            if not dewar_state['fill'][d][step-1]:
                change_dewar_state(d, 'warm', step)


def set_hp_compressor_states(step):
    if linde_storage['bag'][step] > inputs.M_bag_max * inputs.x_bag_setpoint_high_1:
        linde_state['hp_comp_1'][step] = True
    if linde_storage['bag'][step] > inputs.M_bag_max * inputs.x_bag_setpoint_high_2:
        linde_state['hp_comp_2'][step] = True
    if linde_storage['bag'][step] > inputs.M_bag_max * inputs.x_bag_setpoint_high_3:
        linde_state['hp_comp_3'][step] = True
    if linde_storage['bag'][step] < inputs.M_bag_max * inputs.x_bag_setpoint_low_1:
        linde_state['hp_comp_1'][step] = False
    if linde_storage['bag'][step] < inputs.M_bag_max * inputs.x_bag_setpoint_low_2:
        linde_state['hp_comp_2'][step] = False
    if linde_storage['bag'][step] < inputs.M_bag_max * inputs.x_bag_setpoint_low_3:
        linde_state['hp_comp_3'][step] = False


def set_linde_states(step):
    # TODO: handle situation when dewar is being filled and ucn transfer starts to then return to filling the dewar
    # start linde if main dewar level is below threshold
    if linde_storage['dewar'][step-1] < inputs.M_linde_dewar_start:
        linde_state[step]['run'] = True
    # if main dewar is too low, disconnect all consumers
    if linde_storage['dewar'][step-1] < inputs.M_linde_dewar_min:
        linde_state[step]['filling'] = False
        for d in dewars_list:
            if dewar_state['fill'][d][step-1]:
                change_dewar_state(d, 'store', step)
                break
        linde_state['transfer'][step] = False
    else:  # enough helium in main dewar
        # if not transferring, see if transfers needed
        if not linde_state['transfer'][step-1]:
            # if ucn running and level low, start transfer - ucn gets the priority over portable dewars
            if ucn_state['static'][step-1]:
                if linde_storage['ucn'][step-1] < inputs.M_ucn_4K_min:
                    linde_state['transfer'][step] = True
                    # if filling at the moment, stop the fill and place dewar "on the wall"
                    if linde_state['filling'][step-1]:
                        linde_state['filling'][step] = False
                        for d in dewars_list:
                            if dewar_state['fill'][d][step-1]:
                                change_dewar_state(d, 'store', step)
                                break
            # if not transferring or filling now
            if not linde_state[step]['transfer'] and not linde_state[step]['filling']:
                # and have enough liquid in main dewar
                if linde_storage['dewar'][step] > inputs.M_linde_dewar_fill_ok:
                    # and need to fill a portable dewar
                    if we_need_more_dewars(step-1, inputs.prediction_window):
                        d = next_dewar_to_fill_future(step-1, inputs.prediction_window)
                        # then start filling
                        if len(d) > 0:  # if all dewars are busy, wait for empty one to appear
                            linde_state['filling'][step] = True
                            change_dewar_state(d[0], 'fill', step)
        # if transferring, check if ucn is full
        if linde_state[step-1]['transfer']:
            if linde_storage['ucn'][step-1] > inputs.M_ucn_4K_max:
                linde_state[step]['transfer'] = False
        # if filling portable dewar check if it's full
        if linde_state[step-1]['filling']:
            for d in dewars_list:
                if dewar_state['fill'][d][step-1]:
                    # detach if dewar is full
                    if dewar_storage[d][step-1] > inputs.M_portable_dewar_full:
                        change_dewar_state(d, 'store', step)
                        linde_state[step]['filling'] = False
                        break
        # if filling portable dewar check if it has enough LHe and it must be taken at the text step
        if linde_state[step - 1]['filling']:
            for d in dewars_list:
                if dewar_state['fill'][d][step - 1]:
                    if dewar_storage[d][step-1] > inputs.M_portable_dewar_topup:
                        if len(who_needs_dewars(step-1, 2*dt)) > len(find_ready_dewars_now(step)):
                            change_dewar_state(d, 'store', step)
                            linde_state[step]['filling'] = False
                            break
    # if hp storage too low or dewar too high, shutdown linde
    if linde_storage['hp'][step-1] < inputs.M_hp_storage_min:
        linde_state[step]['run'] = False
    if linde_storage['dewar'][step-1] > inputs.M_linde_dewar_max:
        linde_state[step]['run'] = False
    # keep transfer line cold when ucn running
    if ucn_state['static'][step-1]:
        if not linde_state[step]['transfer']:
            linde_state[step]['transfer_trickle'] = True
    # turn off trickle flow if transfer taking place
    if linde_state[step]['transfer']:
        linde_state[step]['transfer_trickle'] = False


def sanity_checks(step):  # yeah, I know
    if linde_state['filling'][step]:
        fail = True
        for d in dewars_list:
            if dewar_state['fill'][d][step]:
                fail = False
                break
        if fail:
            quit_iteration(step, 'linde is filling to nowhere :(')
    if not linde_state['filling'][step]:
        fail = False
        for d in dewars_list:
            if dewar_state['fill'][d][step]:
                fail = True
                break
        if fail:
            quit_iteration(step, 'dewar is filling from nowhere :(')
    ctr = 0
    for d in dewars_list:
        if dewar_state['fill'][d][step]:
            ctr += 1
    if ctr > 1:
        quit_iteration(step, 'filling multiple dewars simultaneously')
    if linde_state['filling'][step] and linde_state['transfer'][step]:
        quit_iteration(step, 'filling ucn and dewar simultaneously')


def quit_iteration(step, msg):
    print(msg)
    update_charts(step)
    plt.savefig('plot.png')
    sys.exit()


def maximize():
    plot_backend = plt.get_backend()
    mng = plt.get_current_fig_manager()
    if plot_backend == 'TkAgg':
        mng.resize(*mng.window.maxsize())
    elif plot_backend == 'wxAgg':
        mng.frame.Maximize(True)
    elif plot_backend == 'Qt4Agg':
        mng.window.showMaximized()


def initialize_charts():
    global fig, ax
    fig, ax = plt.subplots(len(linde_storage.dtype.names)+2, sharex=True)
    plt.tight_layout()
    plt.xlabel('time [days]')
    for i, s in enumerate(linde_storage.dtype.names):
        ax[i].set_title(s)
        charts[s], = ax[i].plot([], [], linewidth=0.5)
    ax[len(linde_storage.dtype.names)].set_title('portable dewars')
    charts['portable dewars'] = {}
    for d in dewars_list:
        charts['portable dewars'][d], = ax[len(linde_storage.dtype.names)].plot([], [], linewidth=0.5)
    ax[len(linde_storage.dtype.names)+1].set_title('purchased dewars')
    charts['purchased dewars'] = {}
    for d in purchased_dewars_list:
        charts['purchased dewars'][d], = ax[len(linde_storage.dtype.names)+1].plot([], [], linewidth=0.5)
    maximize()


def update_charts(step):
    for i, s in enumerate(linde_storage.dtype.names):
        charts[s].set_data(timestamps_days[:step], linde_storage[s][:step])
        ax[i].set_xlim(0, timestamps_days[step])
        ax[i].set_ylim(0, np.max(linde_storage[s][:step]) * 1.05)
    ax[len(linde_storage.dtype.names)].set_xlim(0, timestamps_days[step])
    ax[len(linde_storage.dtype.names)].set_ylim(0, inputs.M_portable_dewar_full * 1.05)
    ax[len(linde_storage.dtype.names)+1].set_xlim(0, timestamps_days[step])
    ax[len(linde_storage.dtype.names)+1].set_ylim(0, inputs.M_portable_dewar_full * 1.05)
    for d in dewars_list:
        charts['portable dewars'][d].set_data(timestamps_days[:step], dewar_storage[d][:step])
    for d in purchased_dewars_list:
        charts['purchased dewars'][d].set_data(timestamps_days[:step], purchased_dewar_storage[d][:step])
    fig.canvas.draw()
    plt.pause(0.1)


def hash_results(ndarrays):
    # logs md5 hashes of final ndarrays
    with open('results.md5', 'w') as f:
        f.write(f'{time.time()}\n')
        for a in ndarrays:
            name = [k for k in globals() if globals()[k] is a][0]
            md5 = hashlib.md5(a).hexdigest()
            f.write(f'{name}: {md5}\n')


if __name__ == "__main__":

    initialize()
    initialize_charts()
    plot_every = 10000

    for i in range(1, total_steps):
        carry_amounts(i)
        carry_states(i)
        set_hp_compressor_states(i)
        set_ucn_states(i)
        set_cmms_states(i)
        set_dewar_states(i)
        set_linde_states(i)
        log_linde_state(i)
        log_dewar_state(i)
        log_ucn_state(i)
        log_cmms_state(i)
        op_hp_compressors(i)
        op_linde(i)
        op_ucn(i)
        op_cmms(i)
        op_dewars(i)
        sanity_checks(i)

        if i % plot_every == 0:
            print(f'step {i}')
            update_charts(i)

    plt.savefig('plot.png')

    hash_results([linde_storage, linde_state, dewar_storage, dewar_state, purchased_dewar_storage, cmms_state, ucn_state])