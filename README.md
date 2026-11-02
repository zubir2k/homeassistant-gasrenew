# 🔥 Gas Renew
[![GitHub Repo stars](https://img.shields.io/github/stars/zubir2k/homeassistant-gasrenew?style=social)](https://github.com/zubir2k/homeassistant-gasrenew/stargazers)
[![hacs_badge](https://img.shields.io/badge/HACS-Integration-41BDF5.svg)](https://github.com/hacs/integration)
![GitHub all releases](https://img.shields.io/badge/dynamic/json?color=41BDF5&logo=home-assistant&label=Download%20Count&suffix=%20installs&cacheSeconds=15600&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.gas_renew.total)
[![Buy](https://img.shields.io/badge/Belanja-Coffee-yellow.svg)](https://zubirco.de/buymecoffee)
[![GitHub Release](https://img.shields.io/github/release/zubir2k/homeassistant-gasrenew.svg)](https://github.com/zubir2k/homeassistant-gasrenew/releases/)

Track how much LPG is left in your cylinder (tong gas). Out of the box it estimates from the days since you last changed it, so no scale or sensor is needed. If you have one, it can count gas only while you're cooking (running sensors) or read it from a scale under the cylinder (weight sensor). Press **Renew** when you fit a new cylinder, and the integration learns how long your cylinders really last.

> v1 replaces the old YAML package (`HAMY/gas_renew`). If you used it, see [Migrating from the YAML package](#migrating-from-the-yaml-package).

## Features

- **UI setup.** Add one entry per cylinder (kitchen, BBQ, shop) from Settings → Devices & services.
- **Three usage sources.** Days since change (no hardware), running time from one or more sensors, or a weight scale. See [How each source is calculated](#how-each-source-is-calculated).
- **Auto-learn.** Each Renew records how many days the old cylinder lasted. The expected duration becomes the average of your last few refills.
- **Energy dashboard.** A `gas` sensor in m³ (`total_increasing`) that accrues your average daily usage every 5 minutes, so it draws even hourly bars.
- **Built-in card.** `custom:gas-renew-card` loads automatically. There's no resource to add.
- **Refill calendar.** Every cylinder appears as a span showing how long it lasted, plus a "Gas expected to run out" event you can trigger on.
- **English and Bahasa Melayu.**
- **Alert blueprint.** Get notified at Low or Critical, and a set number of days before the expected empty date.

## Entities (per cylinder)

| Entity | Notes |
|---|---|
| `sensor.<name>_level` | Full / Medium / Low / Critical. Its attributes feed the card. |
| `sensor.<name>_remaining` | % left |
| `sensor.<name>_remaining_gas` | kg left |
| `sensor.<name>_gas_consumption` | m³, lifetime total, **use this in the Energy dashboard** |
| `sensor.<name>_average_daily_usage` | m³ per day (see [How each source is calculated](#how-each-source-is-calculated)) |
| `sensor.<name>_expected_empty` | timestamp |
| `sensor.<name>_days_in_use` | days since last change |
| `button.<name>_renew` | press when a new cylinder is fitted |
| `number.<name>_expected_duration` | days; auto-learn updates it on Renew |
| `date.<name>_last_change` / `_previous_change` | editable, for backdating |
| `calendar.<name>_refills` | refill history, current cylinder, expected run-out day |

Action: `gas_renew.renew` with any of the cylinder's entities, plus an optional `date` for a renew you forgot to press.

## Installation

### HACS (custom repository)
1. HACS → ⋮ → Custom repositories → add `https://github.com/zubir2k/homeassistant-gasrenew`, category **Integration**.
2. Install **Gas Renew**, then restart Home Assistant.
3. Settings → Devices & services → Add integration → **Gas Renew**.

### Manual
Copy `custom_components/gas_renew` into your `config/custom_components/` and restart.

Requires Home Assistant **2026.3** or newer (for the bundled brand icon).

## The card

```yaml
type: custom:gas-renew-card
entity: sensor.kitchen_lpg_level
# name: Kitchen LPG        # optional, defaults to the device name
# confirm_renew: true      # optional, asks before renewing
```

The cylinder fills to the remaining %. Its colour follows the level: teal, then amber at Low, then red at Critical.

## How each source is calculated

Pick the source under **Configure**. The first page has the source and the common settings (thresholds, m³/kg, learning). The second page shows only the fields for the source you picked. Settings for the other sources are kept, so you can switch back.

All three end in the same numbers: **used kg** for the current cylinder, then

```
remaining kg = cylinder kg − used kg
remaining %  = remaining kg ÷ cylinder kg × 100
level        = Full / Medium / Low / Critical from your thresholds
```

### 1. Days since change (default, no hardware)

```
daily rate     = cylinder kg ÷ expected duration (days)
used kg        = days in use ÷ expected duration × cylinder kg
expected empty = last change + expected duration
```

- It's an average. A heavy cooking week and a week away look the same.
- **Learning:** each Renew records how many days the old cylinder lasted. With auto-learn on, the expected duration becomes the average of the last *N* cylinders ("Refills to average").

### 2. Running time from sensors

**Fields:** Running sensors (one or more), Running threshold, Gas rate per burner.

- Each entity counts as **running** when it's `on`, or, for a numeric sensor (hood power in W, burner temperature in °C), when its value is above the threshold.
- Pick a single cooker-hood sensor, or one sensor per burner. Any number works, so 2-, 3-, 4- and 5-burner stoves are all fine.

```
burner-hours  += elapsed hours × number of entities running   (5-minute steps and on every change)
used kg        = burner-hours × rate (kg per burner-hour)
daily average  = used kg ÷ days in use
expected empty = today + remaining kg ÷ daily average
```

- Two burners for an hour count as two burner-hours, so they use twice the gas of one.
- **Learning:** on Renew, `rate = cylinder kg ÷ burner-hours`. This needs at least 1 burner-hour and a cylinder that lasted at least 7 days. With auto-learn on, the rate is the average of the last *N* cylinders.
- Time when Home Assistant was off isn't counted, because it can't know whether you cooked.

### 3. Weight from a scale sensor

**Fields:** Scale sensor, Method, Empty weight (tare), Auto-renew.

**Scale sensor.** Any numeric sensor with the scale's reading, e.g. an ESPHome `hx711` sensor. Units g, kg, lb and oz are converted; a sensor with no unit is read as kg. Use the scale's **gross** reading (cylinder + platform), not a "gas used" sensor.

**Method.**

| Method | used kg | When to use |
|---|---|---|
| Weight lost since Renew (default) | `scale at Renew − scale now` | No tare needed. Assumes each new cylinder is full. |
| Scale minus tare | `cylinder kg − (scale now − tare)` | You know the empty weight (stamped on the cylinder collar) plus the platform. Handles a part-used cylinder. |

**Filtering.** Load cells are noisy, so:

- **Median.** Remaining gas uses the median of the last 5 readings. The scale is re-read every 5 minutes as well, because HA drops repeated identical values.
- **Only goes down.** Gas only goes one way. A reading that would mean "gas came back" (temperature drift, something resting on the cylinder) is ignored.
- **Lift-off.** A sudden drop of half a cylinder or more means the cylinder was lifted off the scale. It's not counted as use.
- **Swap detection:** a new cylinder is either
  - a rise of half a cylinder or more that holds for 5 minutes, or
  - after a lift-off, coming back at least 1 kg heavier.

  With **Auto-renew** on, that renews automatically, which records the refill, updates the calendar and learning, and makes the new reading the baseline. With it off, the baseline just moves up and you press Renew yourself.
- **Sensor unavailable:** the last good value is kept and `scale_stale: true` is set on the level sensor.

```
daily average  = slope of used kg over the last 14 days (least squares, hourly points)
                 falls back to used kg ÷ days in use until there's a day of data
expected empty = today + remaining kg ÷ daily average
```

- **Learning:** the expected duration still learns from real refill dates.
- **First reading:** switching to weight mid-cylinder anchors the first reading to the current estimate, so the level doesn't jump.

**Hardware hint.** An ESP32/ESP8266 + HX711 + a load cell platform rated above a full cylinder's gross weight (a full 14 kg cylinder weighs roughly 30 kg with its tare). Calibrate in ESPHome with two known weights and add a moving-average filter there too.

## Card layout

<img width="800" alt="gasrenew" src="https://github.com/user-attachments/assets/33ae210b-7661-475a-a63c-98e6c50c79a3" />

The card editor has a **Layout** option. `full` (default) shows the cylinder, %, bar and dates. `compact` shows only the header, the status message and Renew.

```yaml
type: custom:gas-renew-card
entity: sensor.tong_gas_level
mode: compact
```

## Refill calendar

`calendar.<name>_refills` shows:
- **Cylinder #n: lasted X days.** One all-day span per finished cylinder, from fitted to renewed.
- **Cylinder #n in use.** The current one, with its day count and % left.
- **Gas expected to run out.** An all-day event on the expected empty date. It moves whenever you renew, edit the dates or change the duration.

The calendar is read-only. To fix a date, edit the `date` entities or call `gas_renew.renew` with a `date`.

Remind yourself 14 days ahead with a native calendar trigger:

```yaml
triggers:
  - trigger: calendar
    event: start
    entity_id: calendar.kitchen_lpg_refills
    offset: "-336:00:00"   # 14 days before
actions:
  - action: notify.notify
    data:
      title: "🔥 LPG"
      message: "{{ trigger.calendar_event.summary }} on {{ trigger.calendar_event.start }}. Time to order a spare."
```

Upgrading from 1.0.0: your previous → last change dates become Cylinder #1, and every Renew after that is recorded.

## Energy dashboard

Settings → Dashboards → Energy → **Gas consumption** → add `sensor.<name>_gas_consumption`.

How the number is built: every kg added to **used kg** is also added to a lifetime total, and the sensor shows `lifetime kg × m³/kg`. It never goes down, even when you renew.

| Source | What the bars show |
|---|---|
| Days since change | An even daily average in 5-minute steps. On Renew, any gas the estimate hadn't counted yet is added, because the old cylinder is empty. Over time the total equals the cylinders you used. |
| Running time | Gas while burners or the hood run, so bars follow your cooking sessions. On Renew, the uncounted rest of the old cylinder is added. |
| Weight | Gas the scale actually lost. On Renew nothing is added: whatever was left in the old cylinder wasn't burned. |

Changing the duration or the rate never makes the total go down.

### m³ per kg
The default is **0.54 m³/kg** (propane). Butane-rich blends give less gas per kg, so adjust it in the integration's options if you know your supplier's mix. Changing it rescales the lifetime total.

## Options

| Option | Default |
|---|---|
| Medium at or below | 60 % |
| Low at or below | 30 % |
| Critical at or below | 5 % |
| Gas volume per kg | 0.54 m³ |
| Auto-learn duration | on |
| Refills to average | 3 |
| Usage source | Days since change |
| Running threshold *(running time)* | 40 |
| Gas rate per burner *(running time)* | 0.3 kg/h |
| Method *(weight)* | Weight lost since Renew |
| Empty weight / tare *(weight)* | 0 kg |
| Auto-renew *(weight)* | on |

A Renew pressed less than 7 days after the previous one isn't used for learning. A same-day double press is ignored.

## Migrating from the YAML package

1. Note your `input_datetime.gas_last_change`, `gas_previous_change` and `input_number.gas_duration`.
2. Remove `config/HAMY/gas_renew/` (keep the `packages:` line if other HAMY packages use it) and restart.
3. Add the integration with those values. Giving the previous change seeds auto-learn.
4. Replace the old Markdown card with `custom:gas-renew-card`, and the old automation with the blueprint.

## Roadmap

- Possible leak alert: weight dropping while no burner is running.
- Weight + running sensors together, to measure true kg per burner-hour.
- Renew with a known remaining kg for a part-used cylinder.

## Join us

[Home Assistant Malaysia](https://www.facebook.com/groups/homeassistantmalaysia)
