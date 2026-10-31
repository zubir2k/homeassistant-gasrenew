# 🔥 Gas Renew
[![GitHub Repo stars](https://img.shields.io/github/stars/zubir2k/homeassistant-gasrenew?style=social)](https://github.com/zubir2k/homeassistant-gasrenew/stargazers)
[![hacs_badge](https://img.shields.io/badge/HACS-Integration-41BDF5.svg)](https://github.com/hacs/integration)
![GitHub all releases](https://img.shields.io/badge/dynamic/json?color=41BDF5&logo=home-assistant&label=Download%20Count&suffix=%20installs&cacheSeconds=15600&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.gas_renew.total)
[![Buy](https://img.shields.io/badge/Belanja-Coffee-yellow.svg)](https://zubirco.de/buymecoffee)
[![GitHub Release](https://img.shields.io/github/release/zubir2k/homeassistant-gasrenew.svg)](https://github.com/zubir2k/homeassistant-gasrenew/releases/)


Estimate how much LPG is left in your cylinder (tong gas) from the days since you last changed it. No scale or sensor needed. Press **Renew** when you fit a new cylinder, and the integration learns how long your cylinders really last.

> v1 replaces the old YAML package (`HAMY/gas_renew`). If you used it, see [Migrating from the YAML package](#migrating-from-the-yaml-package).

## Features

- **UI setup.** Add one entry per cylinder (kitchen, BBQ, shop) from Settings → Devices & services.
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
| `sensor.<name>_average_daily_usage` | m³ per day (cylinder ÷ duration × m³/kg) |
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

<img width="800" alt="image" src="https://github.com/user-attachments/assets/3518c2bf-22ec-4388-89c2-ca35557e61bb" />

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

How the number is built:
- While a cylinder is in use, it adds `cylinder kg ÷ expected duration × m³/kg` per day, in 5-minute steps.
- It stops adding once the estimate says the cylinder is finished. A tank that outlasts its estimate adds nothing until you renew.
- On **Renew**, any gas the estimate hadn't counted yet is added in one step, because the old cylinder is now empty. Over time the total equals the number of cylinders you actually used.
- Changing the duration never makes the total go down.

The bars are an **average**, not real-time usage. If you want usage per cooking session, see the roadmap.

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

A Renew pressed less than 7 days after the previous one isn't used for learning. A same-day double press is ignored.

## Migrating from the YAML package

1. Note your `input_datetime.gas_last_change`, `gas_previous_change` and `input_number.gas_duration`.
2. Remove `config/HAMY/gas_renew/` (keep the `packages:` line if other HAMY packages use it) and restart.
3. Add the integration with those values. Giving the previous change seeds auto-learn.
4. Replace the old Markdown card with `custom:gas-renew-card`, and the old automation with the blueprint.

## Roadmap

- Optional usage weighting from a cooker-hood power sensor: spread the daily estimate over the hours you actually cook, and calibrate kg/h against real refill history.
- Weight-scale input (ESPHome load cell) for measured readings.

## Join us

[Home Assistant Malaysia](https://www.facebook.com/groups/homeassistantmalaysia)
