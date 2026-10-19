---
title: 策略pine代码拆解学习（6）TP和TL
date: 2022-12-07 14:19:10
tags: pine
---

### 代码片段-L/S variables
#### 源码
```
// L/S variables 
Position = input.string('0', title='1 / 2', options=['0', '1', '2'], group='???')
is_Long  = Position == '1' ? na : true
is_Short = Position == '2' ? na : true
//L/S variables
var bool longCond  = na
var bool shortCond = na
longCond  := nz(longCond[1])
shortCond := nz(shortCond[1])
var int CondIni_long  = 0
var int CondIni_short = 0
CondIni_long  := nz(CondIni_long[1])
CondIni_short := nz(CondIni_short[1])
var bool Final_longCondition  = na
var bool Final_shortCondition = na
Final_longCondition  := nz(Final_longCondition[1])
Final_shortCondition := nz(Final_shortCondition[1])
var bool BT_Final_longCondition  = na
var bool BT_Final_shortCondition = na
BT_Final_longCondition  := nz(BT_Final_longCondition[1])
BT_Final_shortCondition := nz(BT_Final_shortCondition[1])
var float last_open_longCondition  = na
var float last_open_shortCondition = na
var int last_longCondition  = na
var int last_shortCondition = na
var int nLongs  = na
var int nShorts = na
nLongs  := nz(nLongs[1])
nShorts := nz(nShorts[1])
```
#### 官方文档解释

**nz**
以系列中的零(或指定数)替换NaN值。

返回值

`source`的值，如果它不是`na`。如果`source`的值为`na`，则返回0，如果使用1，则返回`replacement`参数。

参数
```
source (series int/float/bool/color) 待执行的系列值。

replacement (series int/float/bool/color) 将替换“source”系列中的所有“na”值的值。
```
**na**
表示“不可用”的关键字，表示变量没有赋值。

**na（x）**
测试 `x` 是否为na。

返回值

如果 `x` 是na，则返回{@on true}，否则返回{@on false}。

#### 对照解读

这些都是一些参数初始化变量，记录订单和持仓情况，用于后续TP和SL

#### ChatGPT解读
这段代码定义了许多变量，包括几个用于跟踪不同条件状态的bool变量。它还定义了几个int变量，用于跟踪多头和空头头寸的数量，以及各种条件的状态。
目前尚不清楚这些变量的用途，也不清楚它们将如何在交易策略中使用。
了解使用此代码的上下文的更多信息将会很有帮助。

### 代码片段-STRATEGY

#### 源码
```
//STRATEGY 
L_1 = RS_Long_condt  and Volume_Breakouts_condt and L_adx and Long_MA
S_1 = RS_Short_condt and Volume_Breakouts_condt and S_adx and Short_MA
L_2 = L_VAP and L_sar
S_2 = S_VAP and S_sar
L_3 = L_rmi and L_sar and Long_MA
S_3 = S_rmi and S_sar and Short_MA
Final_Long_Condt  = L_1 or L_2 or L_3
Final_Short_Condt = S_1 or S_2 or S_3
longCond  := Final_Long_Condt
shortCond := Final_Short_Condt
CondIni_long  :=  longCond[1] ? 1 : shortCond[1] ? -1 : nz(CondIni_long[1])
CondIni_short :=  longCond[1] ? 1 : shortCond[1] ? -1 : nz(CondIni_short[1])
longCondition  =  longCond[1]  and nz(CondIni_long[1])  == -1
shortCondition = shortCond[1] and nz(CondIni_short[1]) == 1
```
#### 对照解读

```
L_1 = RS_Long_condt  and Volume_Breakouts_condt and L_adx and Long_MA
S_1 = RS_Short_condt and Volume_Breakouts_condt and S_adx and Short_MA
L_2 = L_VAP and L_sar
S_2 = S_VAP and S_sar
L_3 = L_rmi and L_sar and Long_MA
S_3 = S_rmi and S_sar and Short_MA
//此段是根据之前得指标结果，穿插使用结合出三对开单指条件

Final_Long_Condt  = L_1 or L_2 or L_3
Final_Short_Condt = S_1 or S_2 or S_3
longCond  := Final_Long_Condt
shortCond := Final_Short_Condt
//Final_Long_Condt 和 Final_Short_Condt是判断是否有多/空信号
//并添加为longCond 和 shortCond子集
CondIni_long  :=  longCond[1] ? 1 : shortCond[1] ? -1 : nz(CondIni_long[1])
CondIni_short :=  longCond[1] ? 1 : shortCond[1] ? -1 : nz(CondIni_short[1])
longCondition  =  longCond[1]  and nz(CondIni_long[1])  == -1
shortCondition = shortCond[1] and nz(CondIni_short[1]) == 1
//此处的意思大概是记录多空订单情况了
```

#### ChatGPT解读
这段代码定义了一些条件，用于确定是进入多头头寸还是空头头寸。
l1和S_1条件用于根据相对强度指数、平均方向指数和成交量来确定是进入多头还是空头。
l2和S_2条件相似，但也考虑了布林带和移动平均。
Final_Long_Condt和Final_Short_Condt变量分别用于组合长仓的l1和l2条件，以及短仓的S_1和S_2条件。
longCond和shortCond变量分别用于跟踪长、短输入条件的状态。
CondIni_long和CondIni_short变量用于跟踪长、短输入条件的初始状态。
longCondition和shortCondition变量用于跟踪多头和空头输入条件当前是否处于活动状态。

### 代码片段-POSITION PRICE

#### 源码
```
// POSITION PRICE
var int last_long_sl = na
var int last_short_sl = na
last_open_longCondition := longCondition ? close[1] : nz(last_open_longCondition[1])
last_open_shortCondition := shortCondition ? close[1] : nz(last_open_shortCondition[1])
last_longCondition := longCondition ? time : nz(last_longCondition[1])
last_shortCondition := shortCondition ? time : nz(last_shortCondition[1])
in_longCondition = last_longCondition > last_shortCondition
in_shortCondition = last_shortCondition > last_longCondition
if longCondition
    nLongs += 1
    nShorts := na
    nShorts
if shortCondition
    nLongs := na
    nShorts += 1
    nShorts
```
#### 对照解读
此段代码用于记录策略发生时的价格和时间


### 代码片段-TP_1

#### 源码
```
//TP_1
tp = input.float(0.8, 'TP-1 [%]', step=0.1, group='Backtesting')
var bool long_tp = na
var bool short_tp = na
var int last_long_tp = na
var int last_short_tp = na
var bool Final_Long_tp = na
var bool Final_Short_tp = na
Final_Long_tp := nz(Final_Long_tp[1])
Final_Short_tp := nz(Final_Short_tp[1])
long_tp := is_Long and high > last_open_longCondition * (1 + tp / 100) and in_longCondition
short_tp := is_Short and low < last_open_shortCondition * (1 - tp / 100) and in_shortCondition
last_long_tp := long_tp ? time : nz(last_long_tp[1])
last_short_tp := short_tp ? time : nz(last_short_tp[1])
Final_Long_tp := long_tp and last_longCondition > nz(last_long_tp[1]) and last_longCondition > nz(last_long_sl[1])
Final_Short_tp := short_tp and last_shortCondition > nz(last_short_tp[1]) and last_shortCondition > nz(last_short_sl[1])
l_1_h = Final_Long_tp ? last_open_longCondition * (1 + tp / 100) : na
s_1_h = Final_Short_tp ? last_open_shortCondition * (1 - tp / 100) : na
//TP_2 
tp2 = input.float(0.9, 'TP-2 [%]', step=0.1)
var bool long_tp2 = na
var bool short_tp2 = na
var int last_long_tp2 = na
var int last_short_tp2 = na
var bool Final_Long_tp2 = na
var bool Final_Short_tp2 = na
Final_Long_tp2 := nz(Final_Long_tp2[1])
Final_Short_tp2 := nz(Final_Short_tp2[1])
long_tp2 := is_Long and high > last_open_longCondition * (1 + tp2 / 100) and in_longCondition
short_tp2 := is_Short and low < last_open_shortCondition * (1 - tp2 / 100) and in_shortCondition
last_long_tp2 := long_tp2 ? time : nz(last_long_tp2[1])
last_short_tp2 := short_tp2 ? time : nz(last_short_tp2[1])
Final_Long_tp2 := long_tp2 and last_longCondition > nz(last_long_tp2[1]) and last_longCondition > nz(last_long_sl[1])
Final_Short_tp2 := short_tp2 and last_shortCondition > nz(last_short_tp2[1]) and last_shortCondition > nz(last_short_sl[1])
l_2_h = Final_Long_tp2 ? last_open_longCondition * (1 + tp2 / 100) : na
s_2_h = Final_Short_tp2 ? last_open_shortCondition * (1 - tp2 / 100) : na
//TP_3 
tp3 = input.float(2.1, ' TP-3 [%]', step=0.1)
var bool long_tp3 = na
var bool short_tp3 = na
var int last_long_tp3 = na
var int last_short_tp3 = na
var bool Final_Long_tp3 = na
var bool Final_Short_tp3 = na
Final_Long_tp3 := nz(Final_Long_tp3[1])
Final_Short_tp3 := nz(Final_Short_tp3[1])
long_tp3 := is_Long and high > last_open_longCondition * (1 + tp3 / 100) and in_longCondition
short_tp3 := is_Short and low < last_open_shortCondition * (1 - tp3 / 100) and in_shortCondition
last_long_tp3 := long_tp3 ? time : nz(last_long_tp3[1])
last_short_tp3 := short_tp3 ? time : nz(last_short_tp3[1])
Final_Long_tp3 := long_tp3 and last_longCondition > nz(last_long_tp3[1]) and last_longCondition > nz(last_long_sl[1])
Final_Short_tp3 := short_tp3 and last_shortCondition > nz(last_short_tp3[1]) and last_shortCondition > nz(last_short_sl[1])
l_3_h = Final_Long_tp3 ? last_open_longCondition * (1 + tp3 / 100) : na
s_3_h = Final_Short_tp3 ? last_open_shortCondition * (1 - tp3 / 100) : na
// SL 
sl = input.float(7.7, 'SL [%]', step=0.1)
var int CondIni_long_sl = 0
var int CondIni_short_sl = 0
var bool Final_Long_sl0 = na
var bool Final_Short_sl0 = na
Final_Long_sl0 := nz(Final_Long_sl0[1])
Final_Short_sl0 := nz(Final_Short_sl0[1])
var bool Final_Long_sl = na
var bool Final_Short_sl = na
Final_Long_sl := nz(Final_Long_sl[1])
Final_Short_sl := nz(Final_Short_sl[1])
long_sl = is_Long and low <= (1 - sl / 100) * last_open_longCondition and not(open < (1 - sl / 100) * last_open_longCondition)
short_sl = is_Short and high >= (1 + sl / 100) * last_open_shortCondition and not(open > (1 + sl / 100) * last_open_shortCondition)
Final_Long_sl0 := Position == 'BOTH' ? long_sl and nz(CondIni_long_sl[1]) == -1 and not Final_Long_tp and not shortCondition : long_sl and nz(CondIni_long_sl[1]) == -1 and not Final_Long_tp
Final_Short_sl0 := Position == 'BOTH' ? short_sl and nz(CondIni_short_sl[1]) == -1 and not Final_Short_tp and not longCondition : short_sl and nz(CondIni_short_sl[1]) == -1 and not Final_Short_tp
last_long_sl := Final_Long_sl ? time : nz(last_long_sl[1])
last_short_sl := Final_Short_sl ? time : nz(last_short_sl[1])
Final_Long_sl := Final_Long_sl0 and last_longCondition > nz(last_long_tp[1]) and last_longCondition > nz(last_long_sl[1])
Final_Short_sl := Final_Short_sl0 and last_shortCondition > nz(last_short_tp[1]) and last_shortCondition > nz(last_short_sl[1])
CondIni_long_sl := Final_Long_tp or Final_Long_sl or Final_shortCondition ? 1 : Final_longCondition ? -1 : nz(CondIni_long_sl[1])
CondIni_short_sl := Final_Short_tp or Final_Short_sl or Final_longCondition ? 1 : Final_shortCondition ? -1 : nz(CondIni_short_sl[1])
```
#### 对照解读
阶梯止盈 和 止损 参数位置的计算

#### ChatGPT解读
这段代码定义了一个名为tp的新输入参数，并使用它来为多头和空头头寸创建跟踪止损。
tp参数指定止损尾随进场价格的百分比。
long_tp和short_tp变量分别用于跟踪长尾和短尾止损条件的状态。
last_long_tp和last_short_tp变量分别用于跟踪最后一次满足长尾止损条件和短尾止损条件的时间。
Final_Long_tp和Final_Short_tp变量用于跟踪多头和空头尾随止损条件当前是否处于活动状态。
l_1_h和s_1_h变量分别用于存储多头和空头仓位被跟踪止损平仓的价格。
这些变量可以用来创建一个交易策略，使用跟踪止损来管理未平仓头寸。


### 代码片段-Backtest
#### 源码
```
// Backtest 
if long
    strategy.entry('L_1', strategy.long, when=ACT_BT and testPeriod)
    strategy.entry('L_2', strategy.long, when=ACT_BT and testPeriod)
    strategy.entry('L_3', strategy.long, when=ACT_BT and testPeriod)


if short
    strategy.entry('S_1', strategy.short, when=ACT_BT and testPeriod)
    strategy.entry('S_2', strategy.short, when=ACT_BT and testPeriod)
    strategy.entry('S_3', strategy.short, when=ACT_BT and testPeriod)


strategy.exit('TP-1_L', 'L_1', profit=math.abs(last_open_longCondition * (1 + tp / 100) - last_open_longCondition) / syminfo.mintick, loss=math.abs(last_open_longCondition * (1 - sl / 100) - last_open_longCondition) / syminfo.mintick)
strategy.exit('TP-2_S', 'S_2', profit=math.abs(last_open_shortCondition * (1 - tp2 / 100) - last_open_shortCondition) / syminfo.mintick, loss=math.abs(last_open_shortCondition * (1 + sl / 100) - last_open_shortCondition) / syminfo.mintick)
strategy.exit('TP-1_S', 'S_1', profit=math.abs(last_open_shortCondition * (1 - tp / 100) - last_open_shortCondition) / syminfo.mintick, loss=math.abs(last_open_shortCondition * (1 + sl / 100) - last_open_shortCondition) / syminfo.mintick)
strategy.exit('TP-2_L', 'L_2', profit=math.abs(last_open_longCondition * (1 + tp2 / 100) - last_open_longCondition) / syminfo.mintick, loss=math.abs(last_open_longCondition * (1 - sl / 100) - last_open_longCondition) / syminfo.mintick)
strategy.exit('TP-3_S', 'S_3', profit=math.abs(last_open_shortCondition * (1 - tp3 / 100) - last_open_shortCondition) / syminfo.mintick, loss=math.abs(last_open_shortCondition * (1 + sl / 100) - last_open_shortCondition) / syminfo.mintick)
strategy.exit('TP-3_L', 'L_3', profit=math.abs(last_open_longCondition * (1 + tp3 / 100) - last_open_longCondition) / syminfo.mintick, loss=math.abs(last_open_longCondition * (1 - sl / 100) - last_open_longCondition) / syminfo.mintick)
```
#### 官方文档解释

**strategy.entry**
这是进入市场的命令。

参数

id (series string) 必要参数。 订单标识符。 可以通过引用其标识来取消或修改订单。

direction (input strategy_direction) 一个必需的参数。市场持仓方向：'strategy.long'为多头，'strategy.short'为空头。

qty (series int/float) 可选参数。交易的合约/股数/手数/单位数量。预设值为'NaN'。

limit (series int/float) 可选参数。订单的限价。若已指定，订单类型是"limit" 或"stop-limit"。其他订单类型为"NaN"。

stop (series int/float) 可选参数。订单的止损价。如果已指定，订单类型为"stop"或"stop-limit"。其他订单类型则为"NaN"。

oca_name (series string) 可选参数。 该订单属于OCA集团名。 如果订单不属于任何OCA集团，则应该有一个空字符。

oca_type (input string) 可选参数。 OCA订单组类型。 允许的值为：strategy.oca.none - 订单不应属于任何特定OCA组; strategy.oca.cancel - 订单应属于OCA组，一旦订单被成交，同一组的所有其他订单将被取消; strategy.oca.reduce - 订单应属于OCA组别，如果订单合同的X数量已被放置，则同一OCA组的其他订单合同数减少X。

comment (series string) 可选参数。订单的其他说明。

alert_message (series string) 当在“创建警报”对话框的“消息”字段中使用{{strategy.order.alert_message}}占位符时，一个可选参数。

**trategy.exit**
这是一个退出指定进场或整个市场地位的命令。

参数

*id (series string)* 必要参数。 订单标识符。 可以通过引用其标识来取消或修改订单。

*from_entry (series string)* 可选参数。以指定进场指令标识符退出。 要退出所有头寸，应使用空字符串。 默认值为空字符串。

*qty (series int/float)* 可选参数。退出交易的合约/股数/手数/单位的数量。默认值为'NaN'。

*qty_percent (series int/float)* 定义平仓的百分比(0-100)。它的优先级低于 'qty' 参数的优先级。可选。默认值为100。

*profit (series int/float)* 可选参数。 利润目标(以点表示)。 如果已指定，当达到指定的利润额(点)时，则以限价订单退出市场头寸。 默认值为“NaN”。

*limit (series int/float)* 可选参数。 利润目标(需指定价格)。 若已指定，则以指定价格(或更好)退出市场头寸。 参数'limit'的优先级高于参数'profit'的优先级(若值非'NaN'，则'limit'取代'profit')。 默认值为“NaN”。

*loss (series int/float)* 可选参数。 止损(以点表示)。 如果已指定，当达到指定的亏损额(点)时，则以停损单退出市场头寸。 默认值为“NaN”。

*stop (series int/float)* 可选参数。 止损(需指定价格)。 如果已指定，则将以指定价格(或更差)退出市场头寸。 参数'止损'的优先级高于参数'损失'的优先级(若值非'NaN'，则'止损'代替'损失')。 默认值为“NaN”。

*trail_price (series int/float)* 可选参数。跟踪止损激活水平(需指定价格)。如果已指定，当达到指定价格水平时，将放置跟踪止损单。在“trail_offset”参数中指定用于确定跟踪止损单初始价格的偏移量(以点计)：X 点低于激活水平以退出多头; X点高于激活水平以退出空头。默认值为“NaN”。

*trail_points (series int/float)* 可选参数。跟踪止损激活水平(利润以点表示)。如果已指定，当达到已计算价格水平(指定利润金额)时，将放置跟踪止损单。在“trail_offset”参数中指定用于确定跟踪止损单初始价格的偏移量(以点计)：X 点低于激活水平以退出多头; X点高于激活水平以退出空头。默认值为“NaN”。

*trail_offset (series int/float)* 可选参数。跟踪止损激活水平(以点表示)。以点计的偏移量用于确定跟踪止损单的初始价格：X 点低于'trail_price' or 'trail_points'以退出多头; X点高于 'trail_price' or 'trail_points'以退出空头。默认值为“NaN”。

*oca_name (series string)* 可选参数。OCA group的名称 (oca_type = strategy.oca.reduce) 获利目标，止损/跟踪止损。如果未指定名称，将自动生成该名称。

*comment (series string)* 关于订单的附加说明。如果指定，则显示在图表上的订单标记附近。可选。默认值为na。

*comment_profit (series string)* 如果退出是通过指定穿过`profit`或`limit`触发的，则有订单的附加说明。如果指定，则取代 `comment` 参数并显示在图表上的订单标记附近。可选。默认值为na。

*comment_loss (series string)* 如果穿过`stop`或`loss`触发退场，则有订单的附加说明。如果指定，则取代 `comment` 参数并显示在图表上的订单标记附近。可选。默认值为na。

*comment_trailing (series string)* 如果退场是通过指定穿过 `trail_offset` 触发的，则有订单的附加说明。如果指定，则取代 `comment` 参数并显示在图表上的订单标记附近。可选。默认值为na。

*alert_message (series string)* 在“创建警报”对话框的“消息”字段中使用时，将替换'{{strategy.order.alert_message}}'占位符的文本。可选。默认值为na。

*alert_profit (series string)* 在“创建警报”对话框的“消息”字段中使用时，将替换'{{strategy.order.alert_message}}'占位符的文本。仅当退场是通过指定穿过 `profit` 或 `limit` 触发时才替换文本。可选。默认值为na。

*alert_loss (series string)* 在“创建警报”对话框的“消息”字段中使用时，将替换'{{strategy.order.alert_message}}'占位符的文本。仅当退场是通过指定穿过 `stop` 或 `loss` 触发时才替换文本。可选。默认值为na。

*alert_trailing (series string)* 在“创建警报”对话框的“消息”字段中使用时，将替换“{{strategy.order.alert_message}}”占位符的文本。仅当退场是通过指定穿过 `trail_offset` 触发时才替换文本。可选。默认值为na。

**syminfo.mintick**
当前品种的最小刻度值。

类型

simple float

#### 对照解读

此段为最后的代码进场出场的指令执行了

#### ChatGPT解读
这段代码使用了strategy.entry()和strategy.exit()函数来实现交易策略。
strategy.entry()函数用于在相应的多头或空头条件为真时输入多头或空头头寸，并且ACT_BT和testPeriod条件也为真。
strategy.exit()函数用于在满足盈亏参数中指定的条件时退出多头或空头头寸。
在本例中，利润和损失参数是基于tp和sl输入参数定义的，这两个输入参数分别指定了目标利润和止损水平。
此代码可用于实现一种交易策略，该策略使用进入和退出条件的组合来管理头寸