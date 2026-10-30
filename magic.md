# Magic documentation

32-bit programming language inspired by `assembly` and `gforth`.

## Basics

You write code in `.mmx` files and compile it to `.cmc` (which contains machine code).

Everything (skipping `$$` custom names) in quotes in `print ""` is printed as text, so if you make a comment inside quotes it wont work.

Dividing by zero gives `0`.

You do math on the first operand in command, so it MUST be a register. In `add m1, 13, m2, 143` all operands after `m1` are going to be added to `m1`. Only first operand we do math on gets changed, all other stay unchanged which means in `add m1, m2`, the number in `m2` is added to `m1` and only `m1` gets changed and `m2` stays unchanged.

Program must start with `#start` and end with `#end`. A program only runs from start to end. After `#end` you can define your custom commands with `!`. You can split main code into sections you can "jump" to. After a program finishes running, it waits on `#end` if you dont put `exit` before it.

Functions are input-triggered code.

If you want to set a custom name for register it must be capital letters only. To use it you have to put the custom name in `$ $`, you can't use special characters and numbers. Register can have only one custom name.

If you want more than one command in a line you have to add `; ` between them.

You have 6 registers (not counting the memory ones). All registers start at `0`. Biggest negative number is `-2147483647` (`-2³¹`) and biggest positive number registers can hold is `2147483647` (`2³¹ - 1`). If you make number in register bigger than max number it becomes opposite number.

`a` and `b` are for general math use.

`c` is for loop count, loop stops when `c` is `0`, it subtracts `1` from the number or adds `1` if number is negative, until it hits `0`.

`d` holds remainder from division. If we divide `7` by `2` we get `3`, and `1` as remainder goes to `d`. Also used for comparing.

`e` and `f` are stack, you can add number to top of a stack using `stackadd -` and take number from top using `stacktake -`, in place of `-` you have to set register from which you take that number. YOU can't DO ANY MATH ON THEM. `e` and `f` can't be operands. Each stack holds up to 4 numbers. If a stack is full, stackadd does nothing and the register keeps its number. If a stack is empty, stacktake puts 0 in the register.

You have `4096` memory registers, they work the same as `a` and `b` registers (hold a number on which you can do math), you use them in the same way as `a` and `b`.
Registers are from `m1` to `m4096`.

## Example

```
#start
print "hello!"
setname a, <NUMBER>
add a, 10; print "added 10 to a, now it is $NUMBER$!"
#section1
add $NUMBER$, 1; print "added 1 to a, now it is $NUMBER$"
if $NUMBER$ is 20
    print "number is now $NUMBER$!"
        else
            jump #section1
exit
#end
```

# Commands

## `add`

`add -, -` adds all operands after `, ` to first operand in command.

`add m1, 10` 10 is added to memory register

`add $EXAMPLE$, m1` number from m1 is added to number in register which has `$EXAMPLE$` set as custom name.

`add a, m1, m2, m3, m4` adds all operand after first operand to first operand.

## `sub`

`sub -, -` subtracts all operands after `, ` from first operand in command. Works like `add`. Only first operand is changed.

## `div`

`div -, -` divides first operand by second operand, max number of operands is 2. Remainder from division goes to register `d`. Second operand stays unchanged, only first is changed.

`div m1, 2` number in `m1` is divided by number `2`.

## `mul`

`mul -, -` multiplies first operand by all operands after first one. Only first operand is changed.

`mul m1, m3, 2, 4` multiplies number in `m1` by number in `m3` and `2` and `4`.

## `move`

`move -, -` moves number from first register to second register, both operands must be registers. Number in first register becomes `0` and number in second register becomes the number from first register. Max number of operands is `2`.

`move m1, $NUMBER$` moves number from `m1` to `$NUMBER$` and sets `m1` to `0`.

## `setname`

`setname -, < >` gives register custom name you can use as `$NAME$`, first operand must be register. In `< >` set name you want that follows rule from [basics](#basics) section.

`setname a, <NUMBER>` gives register `a` name `$NUMBER$`

## `copy`

`copy -, -` copies number from first operand to all operands after first one. All operands after first one must be a register.

`copy $NUMBER$, m1, m4, m2, $EXAMPLE$`

## `jump`

`jump #-` jumps to set section and code continues to execute from that point.

`jump #example` jumps to section named example.

## `print`

`print " "` prints text in quotes, it also can print $NAME$ as number from register you set this custom name for.

`print "you have $NUMBER$ apples!"`

## `if - is - else`, `if - not - else` 

`if - is -` checks if the number in the first operand equals the second.

`if - not -` checks if it does not equal the second.

First operand must be a register or custom name. If the condition is true it runs the code under it, otherwise the else code runs. Both blocks end when the next line has no indent.

```
if $NUMBER$ is 20
    print "number is now $NUMBER$!"
        else
            add $NUMBER$, 1
```

```
if $NUMBER$ not 0
    print "not zero"
        else
            print "zero"
```

## `exit`

`exit` makes the program end, closes it, it is not needed, not adding it makes program continue to run (after running to `#end` it just waits on `#end`)

## `stackadd` and `stack2add`

`stackadd -`, `stack2add -` adds number from first operand on top of a stack and if operand is a register makes that register `0`. You have `2` stacks. Stack `1` is `e` and stack `f` is `2`.
`stacktake -`, `stack2take -` takes number from top of a stack and puts it in register, operand must be a register. Stack `1` is `e` and stack `f` is `2`.

## `return`

`return` returns to the section you jumped from and makes program continue to execute from next line after the line with jump command.

## `random`

`random -` puts random positive or negative number (not bigger than biggest number possible) in operand, operand must be a register.

## `nop`

`nop` does no operation just like in assembly.

## `compare`

`compare -, -` compares first operand with second operand, max number of operands is 2. If first operand is bigger than second it puts 1 into `d`, if equal it puts `0`, if smaller it puts `-1`.

## `skip`

`skip #-` skips section and makes program execute from next section after skipped section when it comes to that skipped section.

## `halt`

`halt` halts the program until resume, functions can still trigger on input and execute their code

## `output`

`output <x> -, -` first and second operand can be plain number or register, first operand is port number and second is output data from `0` to `65535` in 16-bit and `0` to `255` in 8-bit, in `<x>` you must specify port bit size (`<8>`, `<16>`), look at [Hardware functions](#Hardware functions)

## `resume`

`resume` makes program continue to run from line after halt, if the program isn’t halted, resume does nothing. If you halt program the only way to resume will be adding it in some function so you can press some key and unpause it.

## `read`

`read <x> -, -` reads the number from memory adress to set register. First operand is memory adress, it can be `decimal` or `hex`, second is register you read into. In `<x>` you must specify bit mode (`<16>`, `<8>`).

## `write`

`write <x> -, -` writes number to memory adress, first operand is memory adress, it can be `decimal` or `hex`, second operand can be a register or plain number. In `<x>` you must specify bit mode (`<16>`, `<8>`).

## `wait`

`wait -` waits set number of `ms`. `wait 1000` waits `1000 ms`.

## loop

`[ ]` loop start and end, loop stops when `c` is `0`, it subtracts `1` from the number or adds `1` if number is negative until it hits `0`. You can't add any command on the same line as loop start "[".
You can't make loop inside loop. If loop starts with `c` already 0 it doesnt do anything at all and program continues like loop ended.

A simple script that counts down.

```
#start
add c, 10
setname c, <COUNTDOWN>  ~names register 'c' custom name
#sectionwithloop    ~section with loop
[
print "$COUNTDOWN$"    ~ prints the number in 'c' every run
]
#end
```

## Comment

`~-` comment, you can only add it after space on end of a line, one normal space or few or a tab space or few of them works.

# Functions

You add functions after `#end` and one empty line.

Function is input triggered code that works even if program is halted.

You define functions with `@function`

Functions execute their code on set input.

Only one function at a time, when function executes its code and in middle of it another function want to execute, it has to wait (they queue, if `2` or more functions are triggered exactly at same time (at same nanosecond) it just chooses random one).

Example:

```
#start
print "halt!"
halt    ~ program wait for resume
print "function worked!"
exit
#end

@function
    on input <r>
        resume  ~ program continues to execute from line after halt and prints "function worked!"

@function
    on input <h>
        print "wrong key!"  ~ program stays halted bcs you pressed wrong key!
```


## Hardware functions

Port input functions are exactly the same as functions.

If set port inputs something function triggers its code (optional) and saves the input number in set register.

The code after `on port input <x> -, -` is optional. You can set the first operand which is port number as register (the number in register) or as plain number. Second operand must be a register.

In `<x>` you must specify the port bit size. `<8>` is 8-bit and `<16>` is 16-bit.

`on port input <x> -, " "` only executes its code when number in quotes is the number that was recived, it doesnt store it in any register.

A port gives number from `0` to `65535` in 16-bit and `0` to `255` in 8-bit. Every pin is one number, so when there is number from more than `1` pin the numbers add up.

- Pin `0`  = `1`
- Pin `1`  = `2`
- Pin `2`  = `4`
- Pin `3`  = `8`
- Pin `4`  = `16`
- Pin `5`  = `32`
- Pin `6`  = `64`
- Pin `7`  = `128`  8-bit
- Pin `8`  = `256`
- Pin `9`  = `512`
- Pin `10` = `1024`
- Pin `11` = `2048`
- Pin `12` = `4096`
- Pin `13` = `8192`
- Pin `14` = `16384`
- Pin `15` = `32768`  16-bit

All `8`  pins high = `255`   (`8-bit`)
All `16` pins high = `65535` (`16-bit`)

## Examples

```
@function
    on port input <16> $PORT$, m1
```

```
@function
    on port input <16> $PORT$, "8"
        nop
```

```
@function
    on port input <16> 889, $INPUT$
        if $INPUT$ is 8
            print "$INPUT$"
                else
                    nop
```


# Custom commands

You can make custom commands after `#end` like functions, just do one empty line space between like in example above.

Custom commands are commands that when executed they execute their code.

You define command with `!<name>`, name can't have any numbers or special characters.

## Example

```
#start
supersecretcommand
print "click m!"
#end

@function
    on input <m>
        supersecretcommand

!<supersecretcommand>
    print "meow"
```


# Examples

```
#start
print "hello!"
setname a, <NUMBER>
add a, 10; print "added 10 to a, now it is $NUMBER$!"
#section1
add $NUMBER$, 1; print "added 1 to a, now it is $NUMBER$"
if $NUMBER$ is 20
    print "number is now $NUMBER$!"
        else
            jump #section1
exit
#end
```

```
#start
supersecretcommand
print "click m!"
#end

@function
    on input <m>
        supersecretcommand

!<supersecretcommand>
    print "meow"
```

```
#start
print "halt!"
halt    ~ program wait for resume
print "function worked!"
exit
#end

@function
    on input <r>
        resume  ~ program continues to execute from line after halt and prints "function worked!"

@function
    on input <h>
        print "wrong key!"  ~ program stays halted bcs you pressed wrong key!
```

```
#start
add c, 10
setname c, <COUNTDOWN>  ~names register 'c' custom name
#sectionwithloop    ~section with loop
[
print "$COUNTDOWN$"    ~ prints the number in 'c' every run
]
#end
```

```
#start ~ if inside if bcs why not
if a is 20
    if b is 20
        print "both numbers are 20"
        exit
            else
                jump #start
        else
            jump #start
#end

@function
    on input <a>
        add a, 1

@function
    on input <b>
        add b, 1
```

```
#start
setname m1, <APPLES>
setname m2, <PEARS>
setname a, <BOX>
setname d, <LEFTOVER>
add $APPLES$, 10, 5, 2    ~ 17
mul $APPLES$, 3           ~ 51
sub $APPLES$, 1, 2        ~ 48
copy $APPLES$, $PEARS$    ~ both are 48
move $PEARS$, $BOX$       ~ box is 48, pears is 0
div $APPLES$, 5           ~ apples is 9, leftover is 3
print "apples: $APPLES$, pears: $PEARS$, box: $BOX$, leftover: $LEFTOVER$"
exit
#end
```

```
#start
setname a, <FIRST>
setname b, <SECOND>
setname m1, <SAVED>
add $FIRST$, 5; add $SECOND$, 7
stackadd $FIRST$        ~ first is 0, stack 1 holds 5
stackadd $SECOND$       ~ second is 0, stack 1 holds 5, 7
stacktake $FIRST$       ~ first is 7
stacktake $SECOND$      ~ second is 5
stack2add 100           ~ a plain number works too
stack2take $SAVED$      ~ saved is 100
print "first: $FIRST$, second: $SECOND$, saved: $SAVED$"
exit
#end
```

```
#start
setname a, <SCORE>
skip #check
add $SCORE$, 7
jump #check
print "score is $SCORE$"
add $SCORE$, 5
jump #check
print "score is $SCORE$"
#check
compare $SCORE$, 10
if d is -1
    print "too low"
        else
            print "high enough"
return
#end
```

```
#start
setname b, <ROLL>
random a
compare a, 0           ~ d is -1 if a is negative
if d is -1
    mul a, -1          ~ make it positive
        else
            nop
div a, 6               ~ d is now 0 to 5
copy d, $ROLL$
add $ROLL$, 1          ~ 1 to 6
print "you rolled $ROLL$"
exit
#end
```

```
#start
setname c, <LEFT>
setname a, <TOTAL>
add c, 5
[
add $TOTAL$, $LEFT$
print "left: $LEFT$, total: $TOTAL$"
]
print "done, total is $TOTAL$"
exit
#end
```

```
#start
setname a, <PRESSES>
print "press p to count, q to continue"
halt
print "you pressed p $PRESSES$ times"
exit
#end

@function
    on input <p>
        add $PRESSES$, 1
        cheer

@function
    on input <q>
        resume

!<cheer>
    print "pressed!"
```
