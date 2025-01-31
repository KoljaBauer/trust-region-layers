#   Copyright (c) 2021 Robert Bosch GmbH
#   Author: Fabian Otto
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published
#   by the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.

import gym
import fancy_gym
from functools import partial
from typing import Union

from trust_region_projections_step.trajectories.env_normalizer import BaseNormalizer, MovingAvgNormalizer

from stable_baselines3.common.vec_env.subproc_vec_env import SubprocVecEnv


def make_env(env_id: str, seed: int, rank: int) -> callable:
    """
    Returns callable to create gym environment

    Args:
        env_id: gym env ID
        seed: seed for env
        rank: rank if multiple ensv are used

    Returns: callable for env constructor

    """

    def _get_env():
        env = gym.make(env_id)
        env.seed(seed + rank)
        return env

    return _get_env


class NormalizedEnvWrapper(object):

    def __init__(self, env_id: str, n_envs: int = 1, n_test_envs: int = 1, max_episode_length: int = 1000, gamma=0.99,
                 norm_obs: Union[bool, None] = True, clip_obs: Union[float, None] = None,
                 norm_rewards: Union[bool, None] = True, clip_rewards: Union[float, None] = None, seed: int = 1, **kwargs):
        """
        A vectorized gym environment wrapper that normalizes observations and returns.
        Args:
           env_id: ID of training env
           n_envs: Number of parallel envs to run for more efficient sampling.
           max_episode_length: Sets env dones flag to True after n steps. (only necessary if env does not have
                    a time limit).
           gamma: Discount factor for optional reward normalization.
           norm_obs: If true, keeps moving mean and variance of observations and normalizes new observations.
           clip_obs: Clipping value for normalized observations.
           norm_rewards: If true, keeps moving variance of rewards and normalizes incoming rewards.
           clip_rewards: lipping value for normalized rewards.
           seed: Seed for generating envs
        """

        self.max_episode_length = max_episode_length

        func_list = [partial(fancy_gym.make, env_id=env_id, seed=seed + i, max_episode_length=max_episode_length,
                             normalize_obs=norm_obs, **kwargs) for i in range(n_envs)]
        self.env_fns = func_list
        self.envs = SubprocVecEnv(func_list)
        self.envs_test = self.envs # test and train envs are identical in our case

        self.norm_obs = norm_obs
        self.clip_obs = clip_obs
        self.norm_rewards = norm_rewards
        self.clip_rewards = clip_rewards

        ################################################################################################################
        # Support for state normalization or using time as a feature

        self.state_normalizer = BaseNormalizer()
        # We normalize with a Normalization wrapper
        #if self.norm_obs:
        #    # set gamma to 0 because we do not want to normalize based on return trajectory
        #    self.state_normalizer = MovingAvgNormalizer(self.state_normalizer, shape=self.observation_space.shape,
        #                                                center=True, scale=True, gamma=0., clip=clip_obs)
        ################################################################################################################
        # Support for return normalization
        self.reward_normalizer = BaseNormalizer()
        if self.norm_rewards:
            self.reward_normalizer = MovingAvgNormalizer(self.reward_normalizer, shape=(), center=False, scale=True,
                                                         gamma=gamma, clip=clip_rewards)

        ################################################################################################################

        # save last of in env to return later to
        if n_envs:
            self.last_obs = self.envs.reset()

    def step(self, actions):

        obs, rews, dones, infos = self.envs.step(actions)

        self.last_obs = self.state_normalizer(obs)
        rews_norm = self.reward_normalizer(rews)

        self.state_normalizer.reset(dones)
        self.reward_normalizer.reset(dones)

        return self.last_obs.copy(), rews_norm, dones, infos

    def step_test(self, action):

        obs, rews, dones, infos = self.envs_test.step(action)

        obs = self.state_normalizer(obs, update=False)

        # Return unnormalized rewards for testing to assess performance
        return obs, rews, dones, infos

    def reset_test(self):
        obs = self.envs_test.reset()
        return self.state_normalizer(obs, update=False)

    def reset(self):

        self.state_normalizer.reset()
        self.reward_normalizer.reset()

        obs = self.envs.reset()
        return self.state_normalizer(obs)

    def render_test(self, mode="human", **kwargs):
        self.envs_test.render(mode, **kwargs)

    @property
    def observation_space(self):
        if self.envs is not None:
            return self.envs.observation_space
        else:
            return  self.envs_test.observation_space

    @property
    def action_space(self):
        if self.envs is not None:
            return self.envs.action_space
        else:
            return  self.envs_test.action_space
