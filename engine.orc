; Fixed engine for techno-csound-1. Tokens are substituted from validated numbers only.
sr = @SR@
ksmps = 32
nchnls = 2
0dbfs = 1
seed @SEED@
giSine ftgen 0, 0, 16384, 10, 1
gaL init 0
gaR init 0
gaRoomL init 0
gaRoomR init 0
gaEchoL init 0
gaEchoR init 0
gaKickKey init 0

; p1 voice, p2 onset seconds, p3 total sounding duration seconds, p4 amplitude,
; p5 MIDI, p6 pan -1..1, p7 tone, p8 drive, p9 HP Hz, p10 LP Hz,
; p11 room send, p12 echo send, p13 kick duck amount, p14 stem index.
; Compiler-owned p15..p27: enabled, decay ratio, curve, pitch ratio,
; pitch decay, click gain, drive scale, HP, LP, metal blend, clap center,
; clap spread, output compensation dB. Never supplied as JSON DSP controls.
instr 1, 2, 3, 4, 5, 6, 7, 8
 iVoice = int(p1)
 iFreq = cpsmidinn(p5)
 iAttack = min(.002, p3*.1)
 aEnv transeg 0, iAttack, 0, 1, p3-iAttack, -5, 0
 if p15 == 1 then
  iLife = p3*p16
  iVAttack = min(.002,iLife*.1)
  aEnv transeg 0,iVAttack,0,1,iLife-iVAttack,p17,0
 endif
 if iVoice == 1 then
  if p15 == 1 then
   aFreq expon iFreq*p18,min(p19,iLife*.4),iFreq
   aOsc poscil 1,aFreq,giSine
   aEnv transeg 0,.0007,0,1,max(.001,iLife-.0007),p17,0
   aClick rand .12
   aClick butterhp aClick,2500
   aClickEnv expon 1,.01,.001
   aSig = tanh(aOsc*p8*p21)*aEnv + aClick*aClickEnv*p20
  else
  aFreq expon iFreq*(2+p7*3), min(.055,p3*.4), iFreq
  aOsc poscil 1, aFreq, giSine
  ; One oscillator gives coherent body; no independent sub oscillator to cancel it.
  aEnv transeg 0, .0007, 0, 1, p3-.0007, -3.5, 0
  aClick rand .12
  aClick butterhp aClick, 2500
  aClickEnv expon 1, .01, .001
  aSig = tanh(aOsc*p8)*aEnv + aClick*aClickEnv
  endif
  gaKickKey = gaKickKey + aEnv
 elseif iVoice == 2 then
  aSaw vco2 .55, iFreq
  aSub poscil .35, iFreq, giSine
  aSig moogladder aSaw+aSub, min(p10, iFreq*(3+p7*22)), .18+p7*.35
  iRelease = min(.025,p3*.3)
  aEnv linseg 0,iAttack,1,p3-iAttack-iRelease,.65,iRelease,0
  aSig = aSig*aEnv
 elseif iVoice == 3 || iVoice == 4 then
  aNoise rand 1
  if p15 == 1 then
   aM1 poscil .58,6233,giSine
   aM2 poscil .58,8219,giSine
   aM3 poscil .58,10513,giSine
   aMetal = (aM1+aM2+aM3)*.57735026919
   aSig = aNoise*(1-p24)+aMetal*p24
   aSig butterhp aSig,p22*(.8+.4*p7)
   aSig butterlp aSig,p23
  else
  aSig butterhp aNoise, 4500+p7*3000
  endif
  aSig = aSig*aEnv
 elseif iVoice == 5 then
  aNoise rand 1
  if p15 == 1 then
   aSig reson aNoise,p25*(.85+.3*p7),1100,1
   aPulse1 delay aEnv,p26*.5
   aPulse2 delay aEnv,p26
  else
  aSig reson aNoise, 1400+p7*1600, 1100, 1
  aPulse1 delay aEnv,.011
  aPulse2 delay aEnv,.022
  endif
  aSig = aSig*(aEnv+aPulse1*.55+aPulse2*.3)
 elseif iVoice == 6 then
  aMod poscil iFreq*(1+p7*4), iFreq*1.618, giSine
  aSig poscil 1, iFreq+aMod, giSine
  aSig = aSig*aEnv
 elseif iVoice == 7 then
  aOne vco2 .32,iFreq
  aTwo vco2 .22,iFreq*1.004
  aHigh poscil .18,iFreq*1.5,giSine
  aSig moogladder aOne+aTwo+aHigh, min(p10, iFreq*(3+p7*18)), .25
  aEnv transeg 0,.003,0,1,p3-.003,-3,0
  aSig = aSig*aEnv
 else
  aNoise rand 1
  aSig reson aNoise, 400+p7*6000, 1000, 1
  aEnv linseg 0,p3*.65,1,p3*.35,0
  aSig = aSig*aEnv
 endif
 if iVoice != 1 then
  aSig = tanh(aSig*p8)/p8
  aKey follow2 gaKickKey,.001,.11
  aSig = aSig*(1-p13*limit(aKey,0,1))
 endif
 aSig butterhp aSig,p9
 aSig butterlp aSig,p10
 ; A short terminal fade also bounds delayed clap pulses before note deletion.
 aEnd linseg 1,p3*.9,1,p3*.1,0
 aSig = aSig*p4*aEnd
 if p15 == 1 then
  aSig = aSig*ampdb(p27)
 endif
 aL,aR pan2 aSig,(p6+1)*.5
 if iVoice == 5 && p15 == 1 && p26 > .03 then
  ; Short right-channel offset gives the wide clap a bounded stereo spread.
  aR delay aR,.004
 endif
 gaL = gaL+aL
 gaR = gaR+aR
 gaRoomL = gaRoomL+aL*p11
 gaRoomR = gaRoomR+aR*p11
 gaEchoL = gaEchoL+aL*p12
 gaEchoR = gaEchoR+aR*p12
endin

; Shared room and finite, cross-channel dub taps. Never recurse into source buses.
instr 90
 aRL butterhp gaRoomL,280
 aRR butterhp gaRoomR,280
 aPreL delay aRL,.019
 aPreR delay aRR,.027
 aWetL,aWetR reverbsc aPreL,aPreR,@ROOM_FEEDBACK@,@ROOM_DAMPING@,sr,.35
 aEL butterhp gaEchoL,400
 aER butterhp gaEchoR,400
 aEL butterlp aEL,4500
 aER butterlp aER,4500
 aE1L delay aER,@DELAY_SECONDS@
 aE1R delay aEL,@DELAY_SECONDS@
 aE2L delay aEL,@DELAY_SECONDS@*2
 aE2R delay aER,@DELAY_SECONDS@*2
 aE3L delay aER,@DELAY_SECONDS@*3
 aE3R delay aEL,@DELAY_SECONDS@*3
 aE4L delay aEL,@DELAY_SECONDS@*4
 aE4R delay aER,@DELAY_SECONDS@*4
 aDuck follow2 gaKickKey,.001,.13
 aDuck = 1-.35*limit(aDuck,0,1)
 gaL = gaL+((aWetL+.3*aPreL)*@ROOM_GAIN@+(aE1L+@ECHO_DECAY@*aE2L+(@ECHO_DECAY@^2)*aE3L+(@ECHO_DECAY@^3)*aE4L)*@DELAY_GAIN@)*aDuck
 gaR = gaR+((aWetR+.3*aPreR)*@ROOM_GAIN@+(aE1R+@ECHO_DECAY@*aE2R+(@ECHO_DECAY@^2)*aE3R+(@ECHO_DECAY@^3)*aE4R)*@DELAY_GAIN@)*aDuck
endin

; Shared stereo glue, high-passed side signal, final fade, then clear every bus.
instr 99
 aMid = (gaL+gaR)*.5
 aSide butterhp (gaL-gaR)*.5,160
 aL = aMid+aSide
 aR = aMid-aSide
 aControl butterhp aMid,110
 aCL compress2 aL,aControl,-90,-18,-12,1.5,.025,.15,0
 aCR compress2 aR,aControl,-90,-18,-12,1.5,.025,.15,0
 aL = aL*.2+aCL*.8
 aR = aR*.2+aCR*.8
 aFade linseg 1,p3-.3,1,.3,0
 ; Bounded soft saturation is not a true-peak mastering limiter or LUFS target.
 aL = tanh(aL*1.1*@MASTER_GAIN@)/1.1*aFade
 aR = tanh(aR*1.1*@MASTER_GAIN@)/1.1*aFade
 outs aL,aR
 clear gaL,gaR,gaRoomL,gaRoomR,gaEchoL,gaEchoR,gaKickKey
endin
