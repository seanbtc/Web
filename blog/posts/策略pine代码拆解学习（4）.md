---
title: 策略pine代码拆解学习（4）Volume，SAR，RSI，SMA，RMI
date: 2022-12-03 14:19:01
tags: pine
---

### 代码片段-Volume
#### 源码
```
// Volume
// inputs
volume_f_B = input.float(1.9, title='  Volume mult. Breakouts', minval=0, step=0.1, group='Volume (BREAKOUTS)')
sma_length_B = input.int(47, title='  Volume lenght Breakouts', minval=1, group='Volume (BREAKOUTS)')
// condt
Volume_Breakouts_condt = volume > ta.sma(volume, sma_length_B) * volume_f_B
```
#### 官方文档解释

**volume**
当前K线成交量

**ta.sma**
sma函数返回移动平均值

参数
```
source (series int/float) 待执行的系列值

length (series int) K线数量(长度)
```
返回值

`length`K线返回的`source`的简单移动平均线。



#### 对照解读
```
volume_f_B = input.float(1.9, title='  Volume mult. Breakouts', minval=0, step=0.1, group='Volume (BREAKOUTS)')
          //输入float    默认  标题                              最小值     步进      群组
Volume_Breakouts_condt = volume         >         ta.sma(volume, sma_length_B)                    *  volume_f_B
                         当前K线成交量   是否大于   source为volume,length为sma_length_B的移动平均线  乘  输入的volume
//该值后续用于开仓条件
```

### 代码片段-SAR
#### 源码
```
//SAR
// inputs
Sst = input.float(0.91, title='  Sar Start', step=0.01, minval=0.01, group='SAR')
Sinc = input.float(0.1, title='  Sar Int', step=0.01, minval=0.01, group='SAR')
Smax = input.float(0.92, title='  Sar Max', step=0.01, minval=0.01, group='SAR')
// calc
SAR = ta.sar(Sst, Sinc, Smax)
// condt
L_sar = SAR < close
S_sar = SAR > close

```
#### 官方文档解释

**ta.sar**
抛物线转向(抛物线停止和反向)是J. Welles Wilder, Jr.设计的方法，以找出交易市场价格方向的潜在逆转。

返回值

抛物线转向指标。

参数
```
start (simple int/float) 开始。

inc (simple int/float) 增加

max (simple int/float) 最大.
```
**close**
当前K线关闭时的收盘价

#### 对照解读
```
//SAR  逆转指数
Sst = input.float(0.91, title='  Sar Start', step=0.01, minval=0.01, group='SAR') //对应ta.sar的参数start
Sinc = input.float(0.1, title='  Sar Int', step=0.01, minval=0.01, group='SAR')   //对应ta.sar的参数inc
Smax = input.float(0.92, title='  Sar Max', step=0.01, minval=0.01, group='SAR')  //对应ta.sar的参数max
SAR = ta.sar(Sst, Sinc, Smax)  //计算SAR
// condt
L_sar = SAR < close  //逆转指数小于收盘价格
S_sar = SAR > close  //逆转指数大于收盘价格
//该两参数后续都用于开仓条件
```
### 代码片段-RSI
#### 源码
```

// RSI-VWAP
//inputs
RSI_VWAP_length = input.int(45, title='Rsi vwap lenght', group='RSI-VWAP')
// calc
RSI_VWAP = ta.rsi(ta.vwap(close), RSI_VWAP_length)
RSI_VWAP_overSold = 29
RSI_VWAP_overBought = 75
// condt
L_VAP = ta.crossover(RSI_VWAP, RSI_VWAP_overSold)
S_VAP = ta.crossunder(RSI_VWAP, RSI_VWAP_overBought)

```
#### 官方文档解释

**ta.rsi**
相对强度指数。它是使用在最后一个 `length` K线上`source` 的向上和向下变化的`ta.rma()` 计算的。

返回值

相对强弱指标(RSI)

参数
```
source (series int/float) 待执行的系列值。

length (simple int) K线数量(长度).
```
**ta.vwap**
成交量加权平均价格。

**ta.crossover**
返回值

如果`source1`穿过`source2`则为true，否则为false。

参数
```
source1 (series int/float) 第一数据系列。

source2 (series int/float) 第二数据系列。
```
**ta.crossunder**
返回值

如果`source1`在`source2`下交叉，则为true，否则为false。

参数
```
source1 (series int/float) 第一数据系列。

source2 (series int/float) 第二数据系列。
```
#### 对照解读
```
// RSI-VWAP   RSI指数
//inputs
RSI_VWAP_length = input.int(45, title='Rsi vwap lenght', group='RSI-VWAP') //长度默认45
// calc
RSI_VWAP = ta.rsi     (ta.vwap(close),                 RSI_VWAP_length)
         //相对强度指数  参数为close的成交量加权平均价格， length为RSI_VWAP_length
// condt
RSI_VWAP_overSold = 29
RSI_VWAP_overBought = 75
L_VAP = ta.crossover(RSI_VWAP, RSI_VWAP_overSold)
                     //RSI上穿RSI_VWAP_overSold,判断强势
S_VAP = ta.crossunder(RSI_VWAP, RSI_VWAP_overBought)
                      //RSI下穿RSI_VWAP_overSold,判断弱势
//该两参数后续都用于开仓条件
```

### 代码片段-SMA
#### 源码
```
//SMAs 
// inputs
Length1 = input.int(12, title='  1-SMA Lenght', minval=1, group='SMA')
Length2 = input.int(16, title='  2-SMA Lenght', minval=1, group='SMA')
Length3 = input.int(44, title='  3-SMA Lenght', minval=1, group='SMA')
// calc
xPrice = close
SMA1 = ta.sma(xPrice, Length1)
SMA2 = ta.sma(xPrice, Length2)
SMA3 = ta.sma(xPrice, Length3)
// condt
Long_MA = SMA1 < close and SMA2 < close and SMA3 < close
Short_MA = SMA1 > close and SMA2 > close and SMA3 > close
```
#### 官方文档解释

**ta.sma**
sma函数返回移动平均值

参数
```
source (series int/float) 待执行的系列值

length (series int) K线数量(长度)
```
返回值

`length`K线返回的`source`的简单移动平均线。

#### 对照解读
```
//SMAs 指数
// inputs 输入三个默认的int值
Length1 = input.int(12, title='  1-SMA Lenght', minval=1, group='SMA')
Length2 = input.int(16, title='  2-SMA Lenght', minval=1, group='SMA')
Length3 = input.int(44, title='  3-SMA Lenght', minval=1, group='SMA')


// calc
xPrice = close //收盘价赋予xPrice
SMA1 = ta.sma(xPrice, Length1) //计算source为xPrice ，length为Length1的移动平均线SMA1
SMA2 = ta.sma(xPrice, Length2) //计算source为xPrice ，length为Length2的移动平均线SMA2
SMA3 = ta.sma(xPrice, Length3) //计算source为xPrice ，length为Length3的移动平均线SMA3
// condt
Long_MA = SMA1 < close and SMA2 < close and SMA3 < close   //收盘价都大于三个移动平均线
Short_MA = SMA1 > close and SMA2 > close and SMA3 > close  //收盘价都小于三个移动平均线
//该两参数也用于判断趋势强弱 后续都用于开仓条件
```

### 代码片段-RMI 
#### 源码
```
//RMI 
// inputs
RMI_len = input.int(26, title='Rmi Lenght'  , minval=1, group='Relative Momentum Index')
mom     = input.int(11, title='Rmi Momentum', minval=1, group='Relative Momentum Index')
// calc
RMI_os = 32
RMI_ob = 70
RMI(len, m) =>  
    up = ta.ema(math.max(close - close[m], 0), len)
    dn = ta.ema(math.max(close[m] - close, 0), len)
    RMI = dn == 0 ? 0 : 100 - 100 / (1 + up / dn)
    RMI 
// condt
L_rmi = ta.crossover(RMI(RMI_len, mom), RMI_os)
S_rmi = ta.crossunder(RMI(RMI_len, mom), RMI_ob)
```
#### 官方文档解释

**ta.ema**
ema 函数返回指数加权移动平均线。

返回值

`source` 的指数移动平均线，alpha = 2 / (长度 + 1)。

参数
```
source (series int/float) 待执行的系列值。

length (simple int) K线数量(长度).
```
**math.max**
返回多个值中最大的一个。

**ta.crossover**
返回值

如果`source1`穿过`source2`则为true，否则为false。

参数
```
source1 (series int/float) 第一数据系列。

source2 (series int/float) 第二数据系列。
```
**ta.crossunder**
返回值

如果`source1`在`source2`下交叉，则为true，否则为false。

参数
```
source1 (series int/float) 第一数据系列。

source2 (series int/float) 第二数据系列。
```
#### 对照解读
```
//RMI 指数
// inputs
RMI_len = input.int(26, title='Rmi Lenght'  , minval=1, group='Relative Momentum Index')
mom     = input.int(11, title='Rmi Momentum', minval=1, group='Relative Momentum Index')
// calc
RMI_os = 32
RMI_ob = 70
RMI(len, m) =>  //RMI函数，len和m为传入参数
    up = ta.ema       (math.max(close        - close[m],      0), len)
         ema移动平均线  取最大值( 当前收盘价格 - 上m个K线的收盘价，0) 长度
    dn = ta.ema(math.max(close[m] - close, 0), len)
    RMI = dn == 0 ? 0 : 100 - 100 / (1 + up / dn)
    RMI //最终返回的值
// condt
L_rmi = ta.crossover(RMI(RMI_len, mom), RMI_os) //取RMI计算的结果与RMI_os，做上穿判断，判断强势
S_rmi = ta.crossunder(RMI(RMI_len, mom), RMI_ob)//取RMI计算的结果与RMI_ob，做下穿判断，判断弱势
//该两参数也用于判断趋势强弱 后续都用于开仓条件
```
