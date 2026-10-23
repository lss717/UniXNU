/** @file
  Minimal AsmMacroLib compatibility header for the older edk2 used by
  edk2-msm8998.  Newer edk2 renamed AsmMacroIoLib.h; DarwinBoot only needs
  ASM_FUNC and ASM_PFX for AArch64 ELF.

  SPDX-License-Identifier: BSD-2-Clause-Patent
**/

#ifndef ASM_MACRO_LIB_H_
#define ASM_MACRO_LIB_H_

#define ASM_PFX(name)  name

#define _ASM_FUNC(Name, Section)    \
  .global   Name                  ; \
  .section  #Section, "ax"        ; \
  .type     Name, %function       ; \
  .p2align  2                     ; \
  Name:

#define ASM_FUNC(Name)  _ASM_FUNC(ASM_PFX(Name), .text. ## Name)

#endif // ASM_MACRO_LIB_H_
