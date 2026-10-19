---
title: 策略pine代码拆解学习（5）FAST PKAMA、Centred Trend Indicator、BOLINGER BANDS
date: 2022-12-06 14:19:06
tags: pine
---

### 代码片段-FAST PKAMA
#### 源码
```
// FAST PKAMA
// inputs
lengthA = input.int(29, title='  Fast PKAMA Lenght', group='PKAMA')
factorA = input.float(3.5, title='  Fast PKAMA Factor', group='PKAMA')
spA = input.bool(true, title='  Self Powered - Fast PKAMA', group='PKAMA')
// calc
erA = math.abs(ta.change(close, lengthA)) / math.sum(math.abs(ta.change(close)), lengthA)
powA = spA ? 1 / erA : factorA
perA = math.pow(math.abs(ta.change(close, lengthA)) / math.sum(math.abs(ta.change(close)), lengthA), powA)
aA = 0.
aA := perA * src + (1 - perA) * nz(aA[1], src)
// cont
mad_f = aA / aA[1] > .999 and aA / aA[1] < 1.001
```

#### 官方文档解释

**math.abs**
如果 `number` >= 0，`number` 的绝对值为 `number`，否则为 -`number`。

返回`number`的绝对值。

**ta.change**
比较当前 `source` 值与它的值 `length` K线之前的值并返回差值。

**math.sum**
sum函数返回x的最后y值的滑动综合。

返回值

`length`K线返回的`source`总和。

参数
*source (series int/float)* 待执行的系列值。

*length (series int)* K线数量(长度).
**math.pow**
数学幂函数

返回值

`base`提高到`exponent`的幂。如果`base`是一个系列，它是按元素计算的。

参数
*base (series int/float)* 指定要使用的基础。

*exponent (series int/float)* 指定指数。
**nz**
以系列中的零(或指定数)替换NaN值。

返回值

`source`的值，如果它不是`na`。如果`source`的值为`na`，则返回0，如果使用1，则返回`replacement`参数。

参数
*source (series int/float/bool/color)* 待执行的系列值。

*replacement (series int/float/bool/color)* 将替换“source”系列中的所有“na”值的值。
#### ChatGPT解读
使用close输入和lengthA、factorA和spA输入参数来计算mad_f值。如果aA值除以aA之前的值在0.999到1.001之间，mad_f值为真。
为了使用这段代码，您需要为close输入提供一个值。您可能还想考虑调整mad_f值的计算，以考虑aA值或其先前值等于0的可能性，因为目前在这种情况下，代码将产生一个错误。
此外，您可能需要考虑使用更具描述性的变量名来提高代码的可读性。



### 代码片段-Centred Trend Indicator
#### 源码
```
// Centred Trend Indicator
// inputs
length_ = input.int(10, title='  CTI Lenght', group='Centred Trend Indicator')
lag = input.bool(false, title='  CTI Lag Reduction', group='Centred Trend Indicator')
effi = input.bool(true, title='  CTI Efficient', group='Centred Trend Indicator')
// calc
ma = 0.
sma_1 = ta.sma(src, length_)
X = math.sign(src - (effi ? nz(ma[1]) : sma_1))
Req = math.sum(ta.change(src) * X[1], length_)
OPTeq = ta.cum(ta.change(src) * X)
alpha = math.pow(math.max(Req / OPTeq, 0), lag ? .5 : 1)
ma := alpha * src + (1 - alpha) * nz(ma[1], src)
// condt
L_ma = ma > ma[2]
S_ma = ma < ma[2]
```
#### 官方文档解释

**ta.sma**
sma函数返回移动平均值，即x的最后y值，除以y。

返回值

`length`K线返回的`source`的简单移动平均线。

参数
*source (series int/float)* 待执行的系列值。

*length (series int)* K线数量(长度).
**math.sign**
如果“number”为零，则“number”的符号（signum）为零，如果“number”大于0，则为1.0，如果“number”小于0，则为-1.0。

**ta.cum**
`source` 的累积（全部的）总和。换句话说，它是`source`的所有元素的总和。

返回值

系列总和。

参数
```
source (series int/float)
```
#### 对照解读
基于集中趋势指标(CTI)计算多头和空头交易的L_ma和S_ma条件

### 代码片段-BOLINGER BANDS
#### 源码
```
//BOLINGER BANDS ( not a_f ) 
// inputs
length = input.int(36, title=' BB lenght', group='Bollinger Bands')
mult = input.float(1.5, title=' BB mult.', group='Bollinger Bands', step=0.1)
// calc
basis = ta.ema(close, length)
dev = mult * ta.stdev(close, length)
upper = basis + dev
lower = basis - dev
// condt
Long_BB = ta.crossunder(src, lower)
Short_BB = ta.crossover(src, upper)
```
#### 官方文档解释

**ta.ema**
ema 函数返回指数加权移动平均线。在 ema 中，加权因子呈指数下降。它使用以下公式计算：EMA = alpha * source + (1 - alpha) * EMA[1]，其中 alpha = 2 / (length + 1)。

返回值

`source` 的指数移动平均线，alpha = 2 / (长度 + 1)。

参数
*source (series int/float)* 待执行的系列值。

*length (simple int)* K线数量(长度)
**ta.stdev**
返回值

标准差

参数
*source (series int/float)* 待执行的系列值。

*length (series int)* K线数量(长度).

*biased (series bool)* 确定应该使用哪个估计。可选。默认值为true。
备注

如果`biased`为true，函数将使用对整个总体的有偏估计进行计算，如果为false - 对样本的无偏估计。

**ta.crossover**
返回值

如果`source1`穿过`source2`则为true，否则为false。

参数
*source1 (series int/float)* 第一数据系列。

*source2 (series int/float)* 第二数据系列。
**ta.crossunder**
返回值

如果`source1`在`source2`下交叉，则为true，否则为false。

参数
```
source1 (series int/float) 第一数据系列。

source2 (series int/float) 第二数据系列。
```
#### ChatGPT解读
代码定义了两个输入参数volume_f_B和volume_f_，以及基于这些参数的值和历史卷数据的两个条件。
volume_f_B参数与常用的技术分析指标布林带(Bollinger Band)有关，而volume_f_参数则与体积数据的简单移动平均有关。
检查当前卷是否大于该卷的SMA值乘以相应的参数值。
这些条件可以用来创建基于交易量突破的交易策略。