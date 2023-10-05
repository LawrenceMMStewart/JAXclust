import jax
import jax.numpy as jnp
from typing import Callable, Tuple, Any


class Normal:
  """Normal distribution."""

  def sample(self,
             seed: jax.random.PRNGKey,
             sample_shape: Tuple[int]) -> jax.Array:
    return jax.random.normal(seed, sample_shape)

  def log_prob(self, inputs: jax.Array) -> jax.Array:
    return -0.5 * inputs ** 2


def make_pert_solver(solver : Callable,
                          num_samples: int = 1000,
                          sigma: float = 0.1,
                          noise=Normal()) -> Callable:
    """
    Inputs:
        num_samples : number of samples for monte carlo estimate of expectation.
        sigma : noise amplitude perturbations.
        noise : A class following the structure given of the code for Normal.

    Returns:
        forward_pert : Callable with custom JVP.
    """

    @jax.custom_jvp
    def forward_pert(S, ncc, rng):
        samples = noise.sample(seed=rng,
                               sample_shape=(num_samples,) + S.shape)

        Ak_z, Mk_z = jax.vmap(solver, in_axes=(0, None))(S + sigma * samples, ncc)

        # perturbed argmax and its corresponding coincidence / cluster connectivity matrix
        Akeps = jnp.mean(Ak_z, axis=0)
        Mkeps = jnp.mean(Mk_z, axis=0)

        # perturbed value
        max_values = jnp.einsum('nd,nd->n',
                                jnp.reshape(S + sigma * samples,
                                            (num_samples, -1)),
                                jnp.reshape(Ak_z, (num_samples, -1)))
        Fkeps = jnp.mean(max_values)

        return Akeps, Fkeps, Mkeps


    def pert_jvp(tangent, _, S, ncc, rng):

        samples = noise.sample(seed=rng,
                               sample_shape=(num_samples,) + S.shape)


        Ak_z, Mk_z = jax.vmap(solver, in_axes=(0, None))(S + sigma * samples, ncc)


        #argmax jvp
        nabla_z_flat = -jax.vmap(jax.grad(noise.log_prob))(samples.reshape([-1]))
        tangent_flat = 1.0 / (num_samples * sigma) * jnp.einsum(
            'nd,ne,e->d',
            jnp.reshape(Ak_z, (num_samples, -1)),
            jnp.reshape(nabla_z_flat, (num_samples, -1)),
            jnp.reshape(tangent, (-1,)))
        jvp_argmax = jnp.reshape(tangent_flat, S.shape)


        # max jvp
        pert_argmax = jnp.mean(Ak_z, axis=0)
        jvp_max = jnp.sum(pert_argmax * tangent)
        return jvp_argmax, jvp_max, jnp.zeros_like(tangent) # last output is dummy since we never do grad w.r.t M


    forward_pert.defjvps(pert_jvp, None, None)

    return forward_pert



def make_pert_csolver(csolver : Callable,
                           num_samples: int = 1000,
                           sigma: float = 0.1,
                           noise=Normal(),
                           use_bias : bool = True) -> Callable:
    """
    Inputs:
        num_samples : number of samples for monte carlo estimate of expectation.
        sigma : noise amplitude perturbations.
        noise : A class following the structure given of the code for Normal.
        use_bias : Use the bias method in constrained kruskal's.

    Returns:
        forward_pert : Callable with custom JVP.
    """

    @jax.custom_jvp
    def forward_pert(S, ncc, C, rng):
        samples = noise.sample(seed=rng, sample_shape=(num_samples,) + S.shape)
        AkM_z, MkM_z = jax.vmap(csolver, in_axes=(0, None, None))(S + sigma * samples, ncc, C)

        AkMeps = jnp.mean(AkM_z, axis=0)
        MkMeps = jnp.mean(MkM_z, axis=0)

        max_values = jnp.einsum('nd,nd->n',
                                jnp.reshape(S + sigma * samples,
                                            (num_samples, -1)),
                                jnp.reshape(AkM_z, (num_samples, -1)))

        FkMeps = jnp.mean(max_values)
        return AkMeps, FkMeps, MkMeps


    def pert_jvp(tangent, _, S, ncc, C, rng):
        samples = noise.sample(seed=rng, sample_shape=(num_samples,) + S.shape)
        AkM_z, MkM_z = jax.vmap(csolver, in_axes=(0, None, None))(S + sigma * samples, ncc, C)
        # argmax jvp
        nabla_z_flat = -jax.vmap(jax.grad(noise.log_prob))(samples.reshape([-1]))
        tangent_flat = 1.0 / (num_samples * sigma) * jnp.einsum('nd,ne,e->d',
                                                                jnp.reshape(AkM_z, (num_samples, -1)),
                                                                jnp.reshape(nabla_z_flat, (num_samples, -1)),
                                                                jnp.reshape(tangent, (-1,)))

        jvp_argmax = jnp.reshape(tangent_flat, S.shape)

        # max jvp
        pert_argmax = jnp.mean(AkM_z, axis=0)
        jvp_max = jnp.sum(pert_argmax * tangent)
        return jvp_argmax, jvp_max, jnp.zeros_like(tangent) # third is dummy for Mk


    forward_pert.defjvps(pert_jvp, None, None, None)

    return forward_pert

