# helium-inventory-management

## Installation

- clone and pip-install requirements:

```shell script
git clone https://github.com/nagimov/helium-inventory-management
cd helium-inventory-management
python -m pip install -r requirements.txt
```

- run

```shell script
python main.py
```

## General notes

- testing is ~~optional~~ non-existent
    + some minimal sanity checks are done via `assert`s
- no auto-formatter is used
    + not chasing every PEP
    + certain parts are ugly **for a reason**
- classes for the sake of classes are considered evil
- dtype names of ndarrays are uniquely identifiable, e.g.:
    + `'filling'` state of liquefier and `'fill'` state of dewars
    + `'warmup'` state of liquefier and `'warm'` state of dewars
    + `'hp_comp_1'` state of liquefier and `'hp'` name of linde storage
    + etc.
- explicit > implicit
    + a bunch of if-else statements > fancy lambdas
    + explicit assignments > clever dynamically typed function returns
    + long_variable_names_are_okay_no_seriously_they_are
    + namespaces and only implicit imports (no start imports)

## Project description

The following is the description of project files. Please keep this section up-to-date with actual functionality.

### `thermophysical.py`

Contains data describing fluid properties:

- constants (e.g. universal gas constant, helium molar mass)
- functions describing thermophysical properties (e.g. density of helium gas at given pressure and temperature)

### `inputs.py`

Contains **all** necessary input data:

- parameters of every element (capacities, flow rates, heat loads, losses, etc.)
- schedules of all experiments
- setpoints for control loops, trip points for interlocks
- all necessary unit conversion calculations (e.g. converting liquid helium liters per hour to kilograms per second)

The following conventions are used:

- variable names:
    + M - mass (kg)
    + m - mass flow rate (kg/s)
    + V - volume (m^3)
    + v - volumetric flow rate (m^3/s)
    + p - pressure (Pa)
    + d - density (kg/m^3)
    + P - power or heat load (W)
    + q - energy per unit mass (J/kg)
    + t - time
    + x - unitless fraction
- all variables are in SI units (a.k.a. "meters")
    + as a result, helium inventory is tracked in kilograms rather than liquid liters
        * 1 kilogram ~= 8 liquid liters at atmospheric pressure
- if a variable represents non-SI unit, unit is added to the name of the variable
    + in this case corresponding variable in SI is always calculated
        * e.g. `p_hp_storage_min_psi = 500; p_hp_storage_min = p_hp_storage_min_psi * 6894.76`
- if a time variable represents absolute time (i.e. date + time), unix epoch origin is used
    + string time variables should never leave the input file "as is" and should be always converted to unix epoch first

### `main.py`

All the cool stuff is here.

Description of how system elements are modelled:

- UCN source cryostat
    + flows to/from cryostat are simplified as "LHe in, GHe out"
        * recuperative heat exchangers, JT-efficiencies, pumps, etc. are not included
        * shield cooling, evaporation and pumping are combined to a single return stream to the bag
    + heat load is beam dependent: static load without beam, full load with beam
    + source operation and beam time is taken from schedule
    + liquid helium supply rate is controlled by maintaining liquid helium level in 4K pot
        * when level in 4K pot hits the low setpoint, transfer begins at a specified transfer rate
        * during the cooldown, transfer always happens at max withdrawal rate
    + when source is running, minimum amount of trickle flow is always maintained to keep the transfer line cold
        * this amount is such that LHe fully evaporates and becomes 100% saturated vapor after the transfer line  
    + when ucn turns on, initial cooldown period takes place during a specified period of time with increased heat load 
- Linde 1610 liquefier
    + liquid helium production of the liquefier ramps up gradually after each cooldown
        * ramp values for cooldown from "cold" and "warm" states are specified separately
    + during operation of the liquefier, helium is taken from high-pressure storage and delivered as liquid to dewar
    + when liquefier is off, liquid helium boils off from the main dewar at a specified rate
    + liquid helium can be delivered from main dewar to both ucn cryostat and transport dewars at the same time
        * total withdrawal rate from the main dewar is limited at a specified rate, during ucn transfers transport dewars are filled at a slower rate
        * trickle-flow to ucn cryostat is always delivered whenever ucn is on
    + liquefier always starts whenever conditions are appropriate and stops when they aren't
        * enough pressure in high-pressure storage
        * enough free room in main dewar
    + TODO: scheduling of liquefier operation needs is to be implemented
        * only allow startup and shutdown of the liquefier within a specified time window (e.g. 6AM to 6PM)
- portable dewars
    + liquid helium boils off from dewars stored "on the wall" at a specified rate
    + only dewars with liquid helium level above specified threshold can be attached to cmms experiment
    + dewar fills are accompanied with specified losses to the bag
    + dewars that reach 0 level are considered to be warm and require to be cooled down before the next fill
        * during cooldown, liquid helium is transferred to the dewar and then immediately evaporated to the bag
        * cooldown is specified as amount of liquid helium required to transition the dewar from warm to cold state
    + ucn cryostat always fills at a specified LHe transfer rate and reduces available fill rate for transport dewars
        * if liquid helium level in a partially filled dewar is above the threshold, it is considered to be ready to be used
        * if level is below the threshold, dewar is marked as "low" and will be refilled when possible
    + among all the "low" dewars, fill priority is given to the fullest ones in order to create a "full" dewar as
    quickly and cheaply as possible
        * this also results in "abandoning" the dewars with lowest liquid helium levels and their eventual warmup when
        lower number of dewars need to be in circulation, and eliminates unnecessary boil offs from partially filled
        dewars
- high-pressure compressors
    + high-pressure compressors take helium from the bag and deliver it to the high-pressure storage
    + three compressors are set up to start at specified high level bag setpoints and stop at low level setpoints
- cmms experiments and their scheduling (this is likely the trickiest part of the code)
    + cooldown of cmms experiments is not modelled, experiments are considered "cold but empty" when iteration starts
    + whenever an experiment needs a full dewar, it takes the fullest one available from the storage
        * if no dewar available for the experiment when it needs one, the new dewar is "purchased" for this experiment
        * if another dewar was attached to the experiment, it is returned to the storage as "low"
        * if specified max number of dewars to be purchased is exceeded, iteration stops
    + in order to define whether to start filling the dewar, prediction is made on number of dewars that all cmms
    experiments will require within specified period of time in the future
        * if this number is higher than number of full dewars available in storage, dewar fill is started
    + ucn cryostat has a priority over dewar fills
        * rational for this is that full portable dewars can be purchased when necessary for cmms experiments, while
        ucn transfer line cannot be fed from portable dewars
        * if ucn cryostat requires a topup, portable dewar fill is stopped
