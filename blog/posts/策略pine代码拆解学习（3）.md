---
title: 策略pine代码拆解学习（3）ADX
date: 2022-12-02 14:18:56
tags: pine
---

### 代码片段-ADX
#### 源码
```
//ADX
// inputs
ADX_options = input.string('MASANAKAMURA', title='  ADX Option', options=['CLASSIC', 'MASANAKAMURA'], group='ADX')
ADX_len     = input.int(11, title='  ADX Lenght', minval=1, group='ADX')
th          = input.float(12, title='  ADX Treshold', minval=0, step=0.5, group='ADX')

// calc
calcADX(_len) =>
    up = ta.change(high)
    down = -ta.change(low)
    plusDM = na(up) ? na : up > down and up > 0 ? up : 0
    minusDM = na(down) ? na : down > up and down > 0 ? down : 0
    truerange = ta.rma(ta.tr, _len)
    _plus = fixnan(100 * ta.rma(plusDM, _len) / truerange)
    _minus = fixnan(100 * ta.rma(minusDM, _len) / truerange)
    sum = _plus + _minus
    _adx = 100 * ta.rma(math.abs(_plus - _minus) / (sum == 0 ? 1 : sum), _len)
    [_plus, _minus, _adx]
   
calcADX_Masanakamura(_len) =>
    SmoothedTrueRange = 0.0
    SmoothedDirectionalMovementPlus = 0.0
    SmoothedDirectionalMovementMinus = 0.0
    TrueRange = math.max(math.max(high - low, math.abs(high - nz(close[1]))), math.abs(low - nz(close[1])))
    DirectionalMovementPlus = high - nz(high[1]) > nz(low[1]) - low ? math.max(high - nz(high[1]), 0) : 0
    DirectionalMovementMinus = nz(low[1]) - low > high - nz(high[1]) ? math.max(nz(low[1]) - low, 0) : 0
    SmoothedTrueRange := nz(SmoothedTrueRange[1]) - nz(SmoothedTrueRange[1]) / _len + TrueRange
    SmoothedDirectionalMovementPlus := nz(SmoothedDirectionalMovementPlus[1]) - nz(SmoothedDirectionalMovementPlus[1]) / _len + DirectionalMovementPlus
    SmoothedDirectionalMovementMinus := nz(SmoothedDirectionalMovementMinus[1]) - nz(SmoothedDirectionalMovementMinus[1]) / _len + DirectionalMovementMinus
    DIP = SmoothedDirectionalMovementPlus / SmoothedTrueRange * 100
    DIM = SmoothedDirectionalMovementMinus / SmoothedTrueRange * 100
    DX = math.abs(DIP - DIM) / (DIP + DIM) * 100
    adx = ta.sma(DX, _len)
    [DIP, DIM, adx]
    
[DIPlusC, DIMinusC, ADXC] = calcADX(ADX_len)
[DIPlusM, DIMinusM, ADXM] = calcADX_Masanakamura(ADX_len)

DIPlus = ADX_options == 'CLASSIC' ? DIPlusC : DIPlusM
DIMinus = ADX_options == 'CLASSIC' ? DIMinusC : DIMinusM
ADX = ADX_options == 'CLASSIC' ? ADXC : ADXM

// condt
L_adx = DIPlus > DIMinus and ADX > th
S_adx = DIPlus < DIMinus and ADX > th
```
#### 官方文档解释

**ta.change**
比较当前 `source` 值与它的值 `length` K线之前的值并返回差值。

**?:**
三元条件运算符。

**ta.rma**
RSI中使用的移动平均线。它是指数加权移动平均线，alpha加权值 = 1 /长度。

参数
*source (series int/float)* 待执行的系列值。

*length (simple int)* K线数量(长度).
**ta.tr**
返回值

真实范围/ 真实波动幅度。它是math.max(high - low, math.abs(high - close[1]), math.abs(low - close[1]))。

**ta.sma**
sma函数返回移动平均值，即x的最后y值，除以y。

**fixnan**
对于给定的系列，将NaN值替换为先前的非NaN值。

**nz（source）**
以系列中的零(或指定数)替换NaN值。

返回值

`source`的值，如果它不是`na`。如果`source`的值为`na`，则返回0，如果使用1，则返回`replacement`参数。

**/**
除法。适用于数值表达式。

**math.abs**
如果 `number` >= 0，`number` 的绝对值为 `number`，否则为 -`number`。

返回`number`的绝对值。

**math.max**
返回多个值中最大的一个。

**=>**
'=>'运算符用于用户定义的函数声明和switch语句中。

**！=**

是存储过程中赋值的意思

**and**
逻辑 AND。适用于布尔表达式。

**na（x）**
测试 `x` 是否为na。

**na**
表示“不可用”的关键字，表示变量没有赋值。


#### 对照解读
```
// inputs
ADX_options = input.string('MASANAKAMURA', title='  ADX Option', options=['CLASSIC', 'MASANAKAMURA'], group='ADX')
ADX_len     = input.int(11, title='  ADX Lenght', minval=1, group='ADX')
th          = input.float(12, title='  ADX Treshold', minval=0, step=0.5, group='ADX')
//上一篇有类似的解读，意思是一些默认值的设置输入

// calc 
//CLASSIC
calcADX(_len) => //calcADX为自定义的函数，传入_len,经过一系列的计算，最终把值赋予最后一行[_plus, _minus, _adx]
    up = ta.change(high)//比较当前higt值 与上一个hight直接的差值
    down = -ta.change(low)//比较当前low值 与上一个low直接的差值
    plusDM = na(up)  ? na    : up > down and up > 0 ? up : 0 //下方注解一
    minusDM = na(down) ? na : down > up and down > 0 ? down : 0 //类似注解一
    truerange = ta.rma(ta.tr, _len) //移动平均线  
    _plus = fixnan(100 * ta.rma(plusDM, _len) / truerange)  
    //ta.rma(plusDM, _len)计算上沿变化的移动平均线
    //与truerange的计算是为了用于计算趋势
    //fixnan是替换Na值的操作
    _minus = fixnan(100 * ta.rma(minusDM, _len) / truerange)  
    sum = _plus + _minus  //sum = 上沿趋势线和下沿趋势线相加
    _adx = 100 * ta.rma(math.abs(_plus - _minus) / (sum == 0 ? 1 : sum), _len)  
    //math.abs(_plus - _minus)  上下趋势线差值的绝对值
    [_plus, _minus, _adx]
注解一
       if(up值为不可用){
        plusDM = na
    }else if(up > down and up >0){
        plusDM = up
    }else{
        plusDM = 0
    }
//与calcADX其实是不同的计算方式，calcADX为经典公版的adx计算方法，Masanakamura应该是秘制的
//MASANAKAMURA
calcADX_Masanakamura(_len) =>
    SmoothedTrueRange = 0.0
    SmoothedDirectionalMovementPlus = 0.0
    SmoothedDirectionalMovementMinus = 0.0
    TrueRange = math.max(math.max(high - low, math.abs(high - nz(close[1]))), math.abs(low - nz(close[1]))) 
    //math.max 取最大值  
    //close[1] 上一根K线的收盘价格  
    //nz(close[1]) 防止价格为0的操作
    DirectionalMovementPlus = high - nz(high[1]) > nz(low[1]) - low ? math.max(high - nz(high[1]), 0) : 0
    DirectionalMovementMinus = nz(low[1]) - low > high - nz(high[1]) ? math.max(nz(low[1]) - low, 0) : 0
    SmoothedTrueRange := nz(SmoothedTrueRange[1]) - nz(SmoothedTrueRange[1]) / _len + TrueRange
    SmoothedDirectionalMovementPlus := nz(SmoothedDirectionalMovementPlus[1]) - nz(SmoothedDirectionalMovementPlus[1]) / _len + DirectionalMovementPlus
    SmoothedDirectionalMovementMinus := nz(SmoothedDirectionalMovementMinus[1]) - nz(SmoothedDirectionalMovementMinus[1]) / _len + DirectionalMovementMinus
    DIP = SmoothedDirectionalMovementPlus / SmoothedTrueRange * 100
    DIM = SmoothedDirectionalMovementMinus / SmoothedTrueRange * 100
    DX = math.abs(DIP - DIM) / (DIP + DIM) * 100
    adx = ta.sma(DX, _len)
    [DIP, DIM, adx]
//adx为最终获取的趋势移动平均线
//基本每一行都的换算赋值方法都能看懂，但是为什么要这样加就需要继续深入研究
[DIPlusC, DIMinusC, ADXC] = calcADX(ADX_len)
[DIPlusM, DIMinusM, ADXM] = calcADX_Masanakamura(ADX_len)
//根据传入的ADX_len参数，传入对应的函数，获取到的对应值
DIPlus = ADX_options == 'CLASSIC' ? DIPlusC : DIPlusM
DIMinus = ADX_options == 'CLASSIC' ? DIMinusC : DIMinusM
ADX = ADX_options == 'CLASSIC' ? ADXC : ADXM
//根据设置的ADX_options值,来取决于启动什么数据
// condt
L_adx = DIPlus > DIMinus and ADX > th
S_adx = DIPlus < DIMinus and ADX > th
//adx的趋势判断，后续将使用于开单的条件
```


#### ChatGPT解读
根据平均方向指数(ADX)和指定的阈值计算多头和空头交易的L_adx和S_adx条件。ADX计算可以使用经典方法或Masanakamura方法执行，这取决于ADX_options输入的值。
为了使用这段代码，您需要为高输入和低输入提供值。
此外，您可能想要考虑为函数定义添加ADX_options输入的默认值，因为目前如果不提供ADX_options输入，该函数将无法工作。您可能还想考虑使用更具描述性的变量名，以使代码更容易理解。
