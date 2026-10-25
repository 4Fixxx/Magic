Magic documentation
32 Bit programming language inspired by assembly and gforth.



1. Basics

You write code in ".mmx" files and compile to ".cmc" (it contains machine code).

Everything (skipping $$ cutom names) in quotes in 'print ""' is printed as text so if you make comment inside quotes it wont work.

Dividing by zero gives 0.

You do math on the first operand in command, it MUST be a register. In 'add m1, 13, m2, 143' all operands after "m1" are going to be added to 'm1'. Only first operand we do math gets changed, all other stay unchanged which means in 'add m1, m2' number from 'm2' is added to 'm1' and only 'm1' gets changed and 'm2' stays unchanged.

Program must start with '#start' and end with '#end', program only runs from start to end. After '#end' you can define your custom commands with '!'. You can split main code into sections you can "jump" to. After program finishes running it waits on '#end' if you dont put 'exit' before it.

Functions are input-triggered code.

If you want to set a custom name for register it must be capital letters only. To use it you have to put the custom name in '$ $', you cant use special characters and numbers. Register can have only 1 custom name.

If you want more than 1 command in a line you have to add '; ' between them.

You have 6 registers (not counting the memory ones). All registers start at 0. Biggest negative number is -2147483647 and biggest positive number registers can hold is 2147483647. If you make number in register bigger than max number it becomes opposite number.
'a' and 'b' are for general math use.
'c' is for loop count, loop stops when 'c' is 0, it subtracts 1 from the number or adds 1 if number is negative until it hits 0.
'd' holds remainder from division. If we divide 7 by 2 we get 3 and 1 as remainder goes to 'd'. Also used for compare.
'e' and 'f' are stack, you can add number to top of a stack using 'stackadd -' and take number from top using 'stacktake -', in place of '-' you have to set register from which you take that number. YOU CANT DO ANY MATH ON THEM. 'e' and 'f' cant be operands. Each stack holds up to 4 numbers. If a stack is full, stackadd does nothing and the register keeps its number. If a stack is empty, stacktake puts 0 in the register.

You have 4096 memory registers, they work the same as 'a' and 'b' registers (hold a number on which you can do math), you use them in the same way as 'a' and 'b'.
Registers are from m1 to m4096.

Example:

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

2. Commands

'add -, -' adds all operands after ", " to first operand in command.

'add m1, 10' 10 is added to memory register
'add $EXAMPLE$, m1' number from m1 is added to number in register which has "$EXAMPLE$" set as custom name.
'add a, m1, m2, m3, m4' adds all operand after first operand to first operand.


'sub -, -' subtracts all operands after ", " from first operand in command. Works like 'add'. Only first operand is changed.


'div -, -' divides first operand by second operand, max number of operands is 2. Remainder from division goes to register 'd'. Second operand stays unchanged, only first is changed.

'div m1, 2' number in 'm1' is divided by number 2.


'mul -, -' multiplies first operand by all operands after first one. Only first operand is changed.

'mul m1, m3, 2, 4' multiplies number in 'm1' by number in 'm3' and 2 and 4.


'move -, -' moves number from first register to second register, both operands must be registers. Number in first register becomes 0 and number in second register becomes the number from first register. Max number of operands is 2.

'move m1, $NUMBER$' moves number from 'm1' to '$NUMBER$' and sets m1 to 0.


'setname -, < >' gives register custom name you can use as '$NAME$', first operand must be register. In '< >' set name you want that follows rule from "1. Basics" section.

'setname a, <NUMBER>' gives register 'a' name "$NUMBER$"


'copy -, -' copies number from first operand to all operands after first one. All operands after first one must be a register.

'copy $NUMBER$, m1, m4, m2, $EXAMPLE$'


'jump #-' jumps to set section and code continues to execute from that point.

'jump #example' jumps to section named example.


'print " "' prints text in quotes, it also can print $NAME$ as number from register you set this custom name for.

'print "you have $NUMBER$ apples!"'


'if - is - else' checks if number in register set as first operand is second operand, first operand must be a register or custom name. If yes it executes code under it, if no else executes its code. If and else ends when next commands has no space before it.
'if $NUMBER$ is 20
    print "number is now $NUMBER$!"
        else
            add $NUMBER$, 1'


'exit' makes the program end, closes it, it is not needed, not adding it makes program continue to run (after running to #end it just waits on #end)


'stackadd -', 'stack2add -' adds number from first operand on top of a stack and if operand is a register makes that register 0. You have 2 stacks. Stack 1 is 'e' and stack 'f' is 2.

'stacktake -', 'stack2take -' takes number from top of a stack and puts it in register, operand must be a register. Stack 1 is 'e' and stack 'f' is 2.


'return' returns to the section you jumped from and makes program continue to execute from next line after the line with jump command.


'random -' puts random positive or negative number (not bigger than biggest number possible) in operand, operand must be a register.


'nop' does no operation just like in assembly.


'compare -, -' compares first operand with second operand, max number of operands is 2. If first operand is bigger than second it puts 1 into 'd', if equel it puts 0, if smaller it puts -1.


'skip #-' skips section and makes program execute from next section after skipped section when it comes to that skipped section.


'halt' halts the program until resume, functions can still trigger on input and execute their code


'resume' makes program continue to run from line after halt, if the program isn’t halted, resume does nothing. If you halt program the only way to resume will be adding it in some function so you can press some key and unpause it.

'[

]' loop start and end, loop stops when 'c' is 0, it subtracts 1 from the number or adds 1 if number is negative until it hits 0. You cant add any command on the same line as loop start "[".
You cant make loop inside loop. If loop starts with 'c' already 0 it doesnt do anything at all and program continues like loop ended.

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

'~-' comment, you can only add it after space on end of a line, one normal space or few or a tab space or few of them works.

3. Functions

You add functions after '#end' and one empty line.

Function is input triggered code that works even if program is halted.

You define functions with '@function'

Functions execute their code on set input.

Only one function at a time, when function executes its code and in middle of it another function want to execute it has to wait (they queue, if 2 or more functions are triggered exactly at same time (at same nanosecond) it just chooses random one).

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


4. Custom commands

You can make custom commands after '#end' like functions, just do one empty line space between like in example above.

Custom commands are commands that when executed they execute their code.

You define command with '!<name>', name cant have any numbers or special characters.

Example:

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


5. Examples of code

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
