# Effects catalog

Taken from Roblox Studio 0.748.0.7481526. Check it against a newer Studio before relying on a range.

## Built-in files

These ship with Roblox, so they load without an upload. Use them as starting points, then replace them with your own uploads or Creator Store assets that fit the game.

Particle textures (`ParticleEmitter.Texture`):

- `rbxasset://textures/particles/SquareParticle.png`
- `rbxasset://textures/particles/common_alpha.dds`
- `rbxasset://textures/particles/explosion01_core_alpha.png`
- `rbxasset://textures/particles/explosion01_core_main.dds`
- `rbxasset://textures/particles/explosion01_implosion_color.png`
- `rbxasset://textures/particles/explosion01_implosion_main.dds`
- `rbxasset://textures/particles/explosion01_shockwave_main.dds`
- `rbxasset://textures/particles/explosion01_smoke_alpha.dds`
- `rbxasset://textures/particles/explosion01_smoke_color_new.dds`
- `rbxasset://textures/particles/explosion01_smoke_main.dds`
- `rbxasset://textures/particles/explosion_alpha.dds`
- `rbxasset://textures/particles/explosion_color.dds`
- `rbxasset://textures/particles/fire_alpha.dds`
- `rbxasset://textures/particles/fire_color.dds`
- `rbxasset://textures/particles/fire_main.dds`
- `rbxasset://textures/particles/fire_sparks_color.dds`
- `rbxasset://textures/particles/fire_sparks_main.dds`
- `rbxasset://textures/particles/forcefield_alpha.dds`
- `rbxasset://textures/particles/forcefield_glow_alpha.dds`
- `rbxasset://textures/particles/forcefield_glow_color.dds`
- `rbxasset://textures/particles/forcefield_glow_main.dds`
- `rbxasset://textures/particles/forcefield_vortex_color.dds`
- `rbxasset://textures/particles/forcefield_vortex_main.dds`
- `rbxasset://textures/particles/legacy_fire_alpha_color.dds`
- `rbxasset://textures/particles/smoke_color.dds`
- `rbxasset://textures/particles/smoke_main.dds`
- `rbxasset://textures/particles/sparkles_color.dds`
- `rbxasset://textures/particles/sparkles_main.dds`

Sounds (`Sound.SoundId`):

- `rbxasset://sounds/action_falling.ogg`
- `rbxasset://sounds/action_footsteps_plastic.mp3`
- `rbxasset://sounds/action_get_up.mp3`
- `rbxasset://sounds/action_jump.mp3`
- `rbxasset://sounds/action_jump_land.mp3`
- `rbxasset://sounds/action_swim.mp3`
- `rbxasset://sounds/impact_explosion_03.mp3`
- `rbxasset://sounds/impact_water.mp3`
- `rbxasset://sounds/oof.ogg`
- `rbxasset://sounds/ouch.ogg`
- `rbxasset://sounds/volume_slider.ogg`

## Editor ranges

The slider range Studio's Properties window offers. Values outside it may be allowed, but rarely look right.

| Class | Property | Range |
|---|---|---|
| ParticleEmitter | Brightness | 0 to 10 |
| ParticleEmitter | Drag | 0 to 5 |
| ParticleEmitter | FlipbookFramerate | 0 to 30 |
| ParticleEmitter | Lifetime | 0 to 5 |
| ParticleEmitter | LightEmission | 0 to 1 |
| ParticleEmitter | LightInfluence | 0 to 1 |
| ParticleEmitter | Rate | 0 to 100 |
| ParticleEmitter | RotSpeed | -360 to 360 |
| ParticleEmitter | Rotation | -180 to 180 |
| ParticleEmitter | ShapePartial | 0 to 1 |
| ParticleEmitter | Size | 0 to 10 |
| ParticleEmitter | Speed | 0 to 100 |
| ParticleEmitter | Squash | -3 to 3 |
| ParticleEmitter | TimeScale | 0 to 1 |
| ParticleEmitter | Transparency | 0 to 1 |
| ParticleEmitter | VelocityInheritance | 0 to 1 |
| Beam | Brightness | 0 to 10 |
| Beam | CurveSize0 | -10 to 10 |
| Beam | CurveSize1 | -10 to 10 |
| Beam | LightEmission | 0 to 1 |
| Beam | LightInfluence | 0 to 1 |
| Beam | TextureLength | 0 to 5 |
| Beam | TextureSpeed | -1 to 1 |
| Beam | ZOffset | -1 to 1 |
| Trail | Brightness | 0 to 10 |
| Trail | Lifetime | 0 to 20 |
| Trail | LightEmission | 0 to 1 |
| Trail | LightInfluence | 0 to 1 |
| Trail | MinLength | 0 to 1 |
| Trail | TextureLength | 0 to 5 |
| Trail | ZOffset | -1 to 1 |
| Highlight | FillTransparency | 0 to 1 |
| Highlight | OutlineTransparency | 0 to 1 |
| PointLight | Range | 0 to 120 |
| SpotLight | Angle | 0 to 180 |
| SpotLight | Range | 0 to 120 |
| Sound | PlaybackSpeed | 0 to 20 |
| Sound | Volume | 0 to 10 |
| UIStroke | Thickness | 0 to 25 |
| UIStroke | Transparency | 0 to 1 |
| UIGradient | Rotation | -180 to 180 |
| UIGradient | Scale | 0 to 10 |
| UIGradient | Transparency | 0 to 1 |

## Deprecated, don't use

`Sound.play`
