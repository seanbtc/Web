---
title: 策略pine代码拆解学习（2）Support and Resistance
date: 2022-12-01 14:18:52
tags: pine
---

### 代码片段-Support and Resistance
#### 源码
```
// Support and Resistance
// inputs
left = input.int(6, title='  Left', group='Support and Resistance')
right = input.int(5, title='  Right', group='Support and Resistance')
// calc
hih = ta.pivothigh(high, left, right)
lol = ta.pivotlow(low, left, right)
top = ta.valuewhen(hih, high[right], 0)
bot = ta.valuewhen(lol, low[right], 0)
RS_Long_condt = close > top
RS_Short_condt = close < bot
// condt
L_cross = ta.crossover(close, top)
S_cross = ta.crossunder(close, bot)
```
#### 官方文档解释

**input.int**
将input添加到脚本设置的输入标签页，它允许您向脚本用户提供配置选项。此函数将整数输入字段添加到脚本的输入中。

**ta.pivothigh**
此函数返回枢轴高点的价格。如果没有枢轴高点，则返回“NaN”。

**ta.pivotlow**
此函数返回枢轴低点的价格。如果没有枢轴低点，它返回“NaN”。
```
ta.pivotlow(source, leftbars, rightbars) → series float

ta.pivotlow(leftbars, rightbars) → series float
```
参数

**source (series int/float)** 可选参数。数据系列计算值。默认为“Low”。

**leftbars (series int/float)** 左长度。

**rightbars (series int/float)** 右长度。

**ta.valuewhen**
返回第n次最近出现的“condition”为true的K线的“source”系列值。
```
ta.valuewhen(condition, source, occurrence)
```
参数

**condition (series bool)** 要搜索的条件。

**source (series int/float/bool/color)** 要从满足条件的K线返回的值。

**occurrence (simple int)** 条件的出现。编号从0开始并按时间回溯，因此“0”是最近出现的“condition”，“1”是第二个最近出现的，依此类推。必须是整数 >= 0。

**close**
当前K线关闭时的收盘价，或尚未完成的实时K线的最后交易价格。

备注

可使用方括号运算符 []来访问以前的值，例如。 close[1]，close[2]。

**high**
当前最高价。

备注

可使用方括号运算符 []来访问以前的值，例如。 high[1]，high[2]。

**low**
当前最低价。

备注

可使用方括号运算符 []来访问以前的值，例如。low[1]，low[2]。

**ta.crossover**

`source1`-系列被定义为穿越`source2`-系列，如果在当前K线上，`source1` 的值大于`source2` 的值，并且在前一根K线上，`source2` 的值 source1` 小于或等于`source2` 的值。

**ta.crossover(source1, source2) → series bool**

返回值

如果`source1`穿过`source2`则为true，否则为false。

参数
```
source1 (series int/float) 第一数据系列。

source2 (series int/float) 第二数据系列。
```
**ta.crossunder**
`source1`-系列被定义为在 `source2`-系列下方交叉，如果在当前K线上，`source1` 的值小于 `source2` 的值，并且在前一根K线上，`source2` 的值 source1` 大于或等于`source2` 的值。

**ta.crossunder(source1, source2) → series bool**

返回值

如果`source1`在`source2`下交叉，则为true，否则为false。

参数
```
source1 (series int/float) 第一数据系列。

source2 (series int/float) 第二数据系列。
```

#### 对照解读
```
// Support and Resistance
此段代码的备注为Support and Resistance，意思为支持与不支持
inputs为默认的参数
left = input.int(6, title='  Left', group='Support and Resistance')
左   =    默认参数6   标题为  Left    组   ='Support and Resistance’
// calc不知道什么意思
hih = ta.pivothigh(high, left, right) //hih = 当前K线是否为 = 左边6个+右边6个，也就是12跟柱子的最高点柱
```
![](/blog/assets/%E7%AD%96%E7%95%A5pine%E4%BB%A3%E7%A0%81%E6%8B%86%E8%A7%A3%E5%AD%A6%E4%B9%A0%EF%BC%882%EF%BC%89/1.png)

```
top = ta.valuewhen(hih, high[right], 0) //top = 最近一次出现条件为hih时，high[right]的值
```
结合top

![](/blog/assets/%E7%AD%96%E7%95%A5pine%E4%BB%A3%E7%A0%81%E6%8B%86%E8%A7%A3%E5%AD%A6%E4%B9%A0%EF%BC%882%EF%BC%89/2.png)
```
lol = ta.pivotlow(low, left, right) //lol= 当前K线是否为 = 左边6个+右边6个，也就是12跟柱子的最低点柱
```
![](/blog/assets/%E7%AD%96%E7%95%A5pine%E4%BB%A3%E7%A0%81%E6%8B%86%E8%A7%A3%E5%AD%A6%E4%B9%A0%EF%BC%882%EF%BC%89/3.png)

```
bot = ta.valuewhen(lol, low[right], 0)//bot= 最近一次出现条件为lol时，low[right]的值
```
结合bot

![](/blog/assets/%E7%AD%96%E7%95%A5pine%E4%BB%A3%E7%A0%81%E6%8B%86%E8%A7%A3%E5%AD%A6%E4%B9%A0%EF%BC%882%EF%BC%89/4.png)
```
RS_Long_condt = close > top //当前K线收盘价大于top线
RS_Short_condt = close < bot//当前K线收盘价小于bot线
此两Boolean值后续用于开单的条件
L_cross = ta.crossover(close, top)//当前收盘K线上穿top线
S_cross = ta.crossunder(close, bot)//当前收盘K线下穿bot线
此两Boolean值后续用于画线
```

#### ChatGPT解读
基于高、低、近值以及左、右输入计算RS_Long_condt、RS_Short_condt、L_cross和S_cross值。
如果关闭值大于顶部值，RS_Long_condt值为真;如果关闭值小于bot值，RS_Short_condt值为真。如果close值越过top值，则L_cross值为真;如果' closeclose值越过bot值，则S_cross值为真。
为了使用这段代码，你需要high, low和close输入。另外，rs_long_condt和' RS_RS_Short_condt值关闭值为top或bot值

