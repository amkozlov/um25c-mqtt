#!/usr/bin/env python3

import time
import argparse
from dataclasses import dataclass
from enum import auto, Enum, unique

import json
import asyncio
from aiomqtt import Client, MqttError

from um_bt import UMDevice

@unique
class MqttFieldType(Enum):
    NUMERIC = auto()
    BOOL = auto()
    ENUM = auto()
    BUTTON = auto()

@dataclass(frozen=True)
class MyDevice:
    type: str
    sn: str

@dataclass(frozen=True)
class MqttFieldConfig:
    type: MqttFieldType
    setter: bool
    advanced: bool  # Do not export by default to Home Assistant
    home_assistant_extra: dict

MQTT_PREFIX="/myhome"
MQTT_SERVER="localhost"
MQTT_INTERVAL=1

DEVICE_FIELDS = {
  'power':  MqttFieldConfig(
        type=MqttFieldType.NUMERIC,
        setter=False,
        advanced=False,
        home_assistant_extra={
            'name': 'Power',
            'unit_of_measurement': 'W',
            'device_class': 'power',
            'state_class': 'measurement',
            'force_update': True,
        }),
  'energy': MqttFieldConfig(
        type=MqttFieldType.NUMERIC,
        setter=False,
        advanced=False,
        home_assistant_extra={
            'name': 'Energy (group1)',
            'unit_of_measurement': 'mWh',
            'device_class': 'energy',
            'state_class': 'measurement',
            'force_update': True,
        })
    }

def payload(id: str, device: MyDevice, field: MqttFieldConfig) -> str:
            ha_id = id
            payload_dict = {
                'state_topic': f'{MQTT_PREFIX}/state/{device.type}-{device.sn}/{id}',
                'device': {
                    'identifiers': [
                        f'{device.sn}'
                    ],
                    'manufacturer': 'Unknown',
                    'name': f'{device.type} {device.sn}',
                    'model': device.type
                },
                'unique_id': f'{device.sn}_{ha_id}',
                'object_id': f'{device.type}_{ha_id}',
            }
            payload_dict.update(field.home_assistant_extra)

            return json.dumps(payload_dict, separators=(',', ':'))

async def pub_mqtt(topic_prefix, client, device, power_w, energy_mwh):
  if not topic_prefix:
    topic_prefix = f'{MQTT_PREFIX}/state/{device.type}-{device.sn}'
#  topic_prefix = 'um25c/'
  payload = str(power_w)
  await client.publish(topic_prefix + '/power', payload=payload.encode())
  payload = str(energy_mwh)
  await client.publish(topic_prefix + '/energy', payload=payload.encode())

async def pub_mqtt_json(topic_prefix, client, device, data):
  if not topic_prefix:
    topic_prefix = f'{MQTT_PREFIX}/state/{device.type}-{device.sn}'
  payload=json.dumps(data)
  await client.publish(topic_prefix + '/all', payload=payload.encode())

# Publish config
async def init_ha_device(client, device):
  for name, field in DEVICE_FIELDS.items():   
    type = 'number' if field.setter else 'sensor'
    await client.publish(
          f'homeassistant/{type}/{device.sn}_{name}/config',
          payload=payload(name, device, field).encode(),
          retain=True
           )

def parse_args():
  # Parse arguments
  parser = argparse.ArgumentParser(description="MQTT bridge for UM25C USB Meter")
  parser.add_argument("--broker", dest="hostname", type=str, default=MQTT_SERVER, help="Address of the MQTT server")
  parser.add_argument("--interval", dest="interval", type=float, default=MQTT_INTERVAL, help="Polling interval")
  parser.add_argument("--addr", dest="addr", type=str, default=None, help="Address of USB Meter")
  parser.add_argument('--topic-prefix', type=str, dest="topic_prefix", default=None, help='Custom MQTT topic prefix')
  parser.add_argument('--ha-config', action="store_true", help='Publish device metadata for Home Assistant')
  parser.add_argument('--json', dest="out_type", action="append_const", const="json", help='Publish data in JSON')
  parser.add_argument('--plain', dest="out_type", action="append_const", const="plain", help='Publish data as plain numbers')

  args = parser.parse_args()

  if not args.out_type:
    args.out_type = ["json", "plain"] 

  return args

async def main():

  cfg = parse_args()

  umDev = UMDevice(cfg.addr)  
    
  device = MyDevice(type=umDev.type, sn=umDev.sn)

  mqttClient = Client(cfg.hostname)
  if cfg.ha_config:
    async with mqttClient as client:
      await init_ha_device(client, device)

  while True:
    try:
        data = umDev.fetch_data()
        power_w = data["Watts"]
        energy_mwh = data["0_mWh"]

        json = {}
        json["power"] = data["Watts"]
        json["energy"] = data["0_mWh"]

        async with mqttClient as client:
          if "plain" in cfg.out_type:
            await pub_mqtt(cfg.topic_prefix, client, device, power_w, energy_mwh)
          if "json" in cfg.out_type: 
            await pub_mqtt_json(cfg.topic_prefix, client, device, json)

    except RuntimeError as error:
        print(error.args[0])
        time.sleep(2.0)
        continue
    except Exception as error:
        umDev.close()
        raise error

    time.sleep(cfg.interval)

asyncio.run(main())
