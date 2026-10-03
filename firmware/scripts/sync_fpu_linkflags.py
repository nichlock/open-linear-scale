Import("env")

# stm32cube.py only propagates -mthumb/-mcpu into ASFLAGS/CCFLAGS/LINKFLAGS;
# it doesn't know about -mfpu/-mfloat-abi. Without those on the link line too,
# the linker driver picks the toolchain's default (non-hardfp) libgcc/libc
# multilib, which then conflicts with hardfp-compiled object files ("uses VFP
# register arguments" / eabi mismatch). Mirror whatever the environment's own
# build_flags put in CCFLAGS so link-time multilib selection stays consistent.
fpu_flags = [flag for flag in env.get("CCFLAGS", [])
             if flag.startswith("-mfpu") or flag.startswith("-mfloat-abi")]
if fpu_flags:
    env.Append(ASFLAGS=fpu_flags, LINKFLAGS=fpu_flags)
