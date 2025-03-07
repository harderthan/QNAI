"""
This file is go1 standalone python file.
"""

# Copyright (c) 2021, NVIDIA CORPORATION.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.
#

import argparse
import json
import os
import numpy as np

from omni.isaac.kit import SimulationApp

simulation_app = SimulationApp({"headless": False})

from omni.isaac.core import World
from omni.isaac.core.utils.prims import define_prim
from omni.isaac.core.utils.prims import get_prim_at_path
from omni.isaac.core.utils.nucleus import get_assets_root_path
import omni.appwindow  # Contains handle to keyboard

import carb
from utils.unitree import Unitree


class Go1Runner(object):
    """[summary]
        Main class to run the simulation
    """

    def __init__(self, physics_dt, render_dt, way_points=None) -> None:
        """[summary]
            creates the simulation world with preset physics_dt and render_dt and creates a unitree a1 robot inside the warehouse
            Argument:
            physics_dt {float} -- Physics downtime of the scene.
            render_dt {float} -- Render downtime of the scene.
            way_points {List[List[float]]} -- x coordinate, y coordinate, heading (in rad)
        """
        self._world = World(stage_units_in_meters=1.0,
                            physics_dt=physics_dt,
                            rendering_dt=render_dt)

        assets_root_path = get_assets_root_path()
        if assets_root_path is None:
            carb.log_error("Could not find Isaac Sim assets folder")

        # spawn scene
        prim = get_prim_at_path("/World/Warehouse")
        if not prim.IsValid():
            prim = define_prim("/World/Warehouse", "Xform")
            asset_path = assets_root_path + "/Isaac/Environments/Simple_Warehouse/warehouse.usd"
            prim.GetReferences().AddReference(asset_path)

        # TODO: change it our environment
        current_script_directory = os.path.dirname(os.path.abspath(__file__))

        assets_root_path = current_script_directory
        # if assets_root_path is None:
        #     carb.log_error("Could not find Isaac Sim assets folder")
        #     simulation_app.close()
        #     sys.exit()

        # print("asset_path: ", assets_root_path)

        # # spawn scene
        # prim = get_prim_at_path("/World/hospital")
        # if not prim.IsValid():
        #     prim = define_prim("/World/hospital", "Xform")
        #     env_asset_path = os.path.join(assets_root_path, "Assets/Envs/hospital2.usd")
        #     print(env_asset_path)
        #     prim.GetReferences().AddReference(env_asset_path)

        robot_usd_path = os.path.join(assets_root_path, "Assets/Robots/go1.usd")
        self._robot = self._world.scene.add(
            Unitree(prim_path="/World/go1",
                    name="go1",
                    usd_path=robot_usd_path,
                    position=np.array([0, 0, 0.40]),
                    physics_dt=physics_dt,
                    model="go1",
                    way_points=way_points,
                    use_ros=True))

        self._world.reset()
        self._enter_toggled = 0
        self._base_command = [0.0, 0.0, 0.0, 0]
        self._event_flag = False
        # bindings for keyboard to command
        self._input_keyboard_mapping = {
            # forward command
            "NUMPAD_8": [1.8, 0.0, 0.0],
            "UP": [1.8, 0.0, 0.0],
            # back command
            "NUMPAD_2": [-1.8, 0.0, 0.0],
            "DOWN": [-1.8, 0.0, 0.0],
            # left command
            "NUMPAD_6": [0.0, -1.8, 0.0],
            "RIGHT": [0.0, -1.8, 0.0],
            # right command
            "NUMPAD_4": [0.0, 1.8, 0.0],
            "LEFT": [0.0, 1.8, 0.0],
            # yaw command (positive)
            "NUMPAD_7": [0.0, 0.0, 1.0],
            "N": [0.0, 0.0, 1.0],
            # yaw command (negative)
            "NUMPAD_9": [0.0, 0.0, -1.0],
            "M": [0.0, 0.0, -1.0],
        }

    @property
    def world(self) -> World:
        """[summary]
            Returns the world object
        """
        return self._world

    def setup(self, way_points=None) -> None:
        """[summary]
            Set unitree robot's default stance, set up keyboard listener and add physics callback
        """

        self._robot.set_state(self._robot.default_a1_state)
        self._appwindow = omni.appwindow.get_default_app_window()
        self._input = carb.input.acquire_input_interface()
        self._keyboard = self._appwindow.get_keyboard()
        self._sub_keyboard = self._input.subscribe_to_keyboard_events(
            self._keyboard, self._sub_keyboard_event)
        self._world.add_physics_callback("a1_advance",
                                         callback_fn=self.on_physics_step)

        if way_points is None:
            self._path_follow = False
        else:
            self._path_follow = True

    def on_physics_step(self, step_size) -> None:
        """[summary]
            Physics call back, switch robot mode and call robot advance function to compute and apply joint torque
        """

        if self._event_flag:
            self._robot.qp_controller.switch_mode()
            self._event_flag = False

        self._robot.advance(step_size, self._base_command, self._path_follow)

    def run(self) -> None:
        """[summary]
            Step simulation based on rendering downtime
        """
        # change to sim running
        while simulation_app.is_running():
            self._world.step(render=True)

    def _sub_keyboard_event(self, event) -> bool:
        """[summary]
            Keyboard subscriber callback to when kit is updated.
        """
        # reset event
        self._event_flag = False
        # when a key is pressed for released  the command is adjusted w.r.t the key-mapping
        if event.type == carb.input.KeyboardEventType.KEY_PRESS:
            # on pressing, the command is incremented
            if event.input.name in self._input_keyboard_mapping:
                self._base_command[0:3] += np.array(
                    self._input_keyboard_mapping[event.input.name])
                self._event_flag = True

            # enter, toggle the last command
            if event.input.name == "ENTER" and self._enter_toggled is False:
                self._enter_toggled = True
                if self._base_command[3] == 0:
                    self._base_command[3] = 1
                else:
                    self._base_command[3] = 0
                self._event_flag = True

        elif event.type == carb.input.KeyboardEventType.KEY_RELEASE:
            # on release, the command is decremented
            if event.input.name in self._input_keyboard_mapping:
                self._base_command[0:3] -= np.array(
                    self._input_keyboard_mapping[event.input.name])
                self._event_flag = True
            # enter, toggle the last command
            if event.input.name == "ENTER":
                self._enter_toggled = False
        # since no error, we are fine :)
        return True


parser = argparse.ArgumentParser(description="a1 quadruped demo")
parser.add_argument("-w",
                    "--waypoint",
                    type=str,
                    metavar="",
                    required=False,
                    help="file path to the waypoints")
args, unknown = parser.parse_known_args()


def main():
    """[summary]
        Parse arguments and instantiate A1 runner
    """
    physics_downtime = 1 / 400.0
    if args.waypoint:
        waypoint_pose = []
        try:
            print(str(args.waypoint))
            with open(str(args.waypoint), encoding="utf-8") as file:
                waypoint_data = json.load(file)
                for waypoint in waypoint_data:
                    waypoint_pose.append(
                        np.array(
                            [waypoint["x"], waypoint["y"], waypoint["rad"]]))
            # print(str(waypoint_pose))

        except FileNotFoundError:
            print("error file not found, ending")
            simulation_app.close()
            return

        runner = Go1Runner(physics_dt=physics_downtime,
                           render_dt=16 * physics_downtime,
                           way_points=waypoint_pose)
        simulation_app.update()
        runner.setup(way_points=waypoint_pose)
    else:
        runner = Go1Runner(physics_dt=physics_downtime,
                           render_dt=16 * physics_downtime,
                           way_points=None)
        simulation_app.update()
        runner.setup(None)

    # an extra reset is needed to register
    runner.world.reset()
    runner.world.reset()
    runner.run()
    simulation_app.close()


if __name__ == "__main__":
    main()
