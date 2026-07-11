// Monster trash talk shared by practice and bot pages.
// Keys include both legacy monster families and the current RPG art keys.

const _TRASH = {
  default: {
    enter: [
      '契約已亮起。落子吧，挑戰者。',
      '棋盤打開了，讓我看看你的第一手。',
      '別急著害怕，先把氣數清楚。'
    ],
    taunt: [
      '這一手，真的算清楚了嗎？',
      '你的破綻在棋盤上閃閃發亮。',
      '再猶豫一下，我就把缺口撕開。'
    ],
    hurt: [
      '唔，這一手有點意思。',
      '你居然看到了那口氣。',
      '這下輪到我重新計算了。'
    ],
    low_hp: [
      '還沒結束，我還有最後一口氣。',
      '別以為優勢已經到手。',
      '終局前的鬆手，最容易付出代價。'
    ],
    die: [
      '這盤，是你贏了。',
      '我記住這一手了。',
      '契約完成。下一次，我會更難纏。'
    ]
  },

  slime: {
    enter: ['噗嚕。先從基本氣開始吧。', '我很軟，但你的棋可不能軟。', '新手村的棋盤，也會咬人喔。'],
    taunt: ['噗，這裡少算一氣。', '貼太緊了，小心被我黏住。', '你的形狀有點滑掉了。'],
    hurt: ['噗嚕！被打散了。', '這手有筋。', '軟歸軟，我也是會痛的。'],
    low_hp: ['等等，我還能再黏一下。', '只剩一小團了。', '不要把最後一氣也拿走。'],
    die: ['噗...化成經驗值了。', '好吧，你通過第一關。', '我會在下一攤泥裡等你。']
  },

  goblin_guard: {
    enter: ['站住。提子訓練從我這關開始。', '想過橋，先證明你會數氣。', '守衛到位，棋盤封鎖。'],
    taunt: ['那顆棋快沒氣了。你沒看見？', '亂衝會被我一網打盡。', '守不住的形，叫我最喜歡。'],
    hurt: ['嘖，封鎖線被破了。', '你找到斷點了。', '這手提得乾淨。'],
    low_hp: ['守衛還沒倒下。', '最後一道門還在。', '你要補上最後一刀才算。'],
    die: ['門開了，進去吧。', '守衛撤退。', '今天算你通行。']
  },

  cave_bat: {
    enter: ['洞窟很暗，但你的弱點很亮。', '吱。快棋和讀氣，我都擅長。', '別眨眼，我會從斷點飛出來。'],
    taunt: ['那裡有空隙，我聽見了。', '慢一拍，就被我穿過去。', '你守的是影子，不是要點。'],
    hurt: ['翅膀被夾住了。', '這一下抓得準。', '可惡，飛不出去了。'],
    low_hp: ['我還能繞最後一圈。', '洞口就在旁邊。', '別讓我逃進暗處。'],
    die: ['吱...洞窟安靜了。', '這次被你看穿了。', '我的回聲會提醒下一隻。']
  },

  goblin_raider: {
    enter: ['雙叫吃突襲隊，出陣！', '你的兩邊，我都想咬。', '別只顧一邊，另一邊已經漏風了。'],
    taunt: ['二選一？你恐怕兩邊都救不了。', '貪吃一顆，送我一串。', '突襲成功的味道真香。'],
    hurt: ['竟然兩邊都補到了？', '突襲路線被堵死了。', '你這手防得漂亮。'],
    low_hp: ['撤退？不，我還要再搶一次。', '只差一個斷點。', '我的隊伍還沒散。'],
    die: ['突襲失敗，收隊。', '你守住了兩翼。', '下次我會帶更多陷阱。']
  },

  orc_grunt: {
    enter: ['獸人小兵上場。硬碰硬吧。', '厚實的棋，才扛得住我的斧頭。', '我不花俏，只劈弱棋。'],
    taunt: ['你的棋太薄了。', '這種形，一斧就裂。', '逃？你有路嗎？'],
    hurt: ['斧頭被架住了。', '這手厚起來了。', '唔，力氣被借走了。'],
    low_hp: ['獸人不會輕易倒下。', '我還能再劈一手。', '別讓我找到反打。'],
    die: ['斧頭落地。', '你比看起來結實。', '這一戰，我服。']
  },

  orc_shield: {
    enter: ['盾牆立起。做眼與厚壁，由我考你。', '想攻進來？先找活路。', '厚棋面前，莽撞會碎。'],
    taunt: ['這裡沒有眼。', '你撞上盾了。', '薄味會自己回來找你。'],
    hurt: ['盾角被撬開了。', '你找到眼位了。', '這手讓我退了一步。'],
    low_hp: ['盾還剩最後一層。', '別停，停了我就補厚。', '我還能撐住。'],
    die: ['盾牆崩解。', '你的活棋成立了。', '防線交給你了。']
  },

  forest_spirit: {
    enter: ['森林會記住每一手棋。', '輕一點，別驚醒弱點。', '在枝葉之間找出正著吧。'],
    taunt: ['你踩斷了自己的退路。', '看似安靜的地方，藏著手筋。', '別把先手送進林裡。'],
    hurt: ['葉脈被切開了。', '這手很清澈。', '你聽見森林的答案了。'],
    low_hp: ['最後一片葉還沒落下。', '我會用殘枝纏住你。', '森林仍有餘音。'],
    die: ['風停了，你通過了。', '森林讓路。', '願你的下一手也如此安靜。']
  },

  mist_dryad: {
    enter: ['霧林手筋師，請你入局。', '看不清時，先找最急的棋。', '霧會遮住形，但遮不住氣。'],
    taunt: ['你追的是幻影。', '真正的要點不在那裡。', '霧裡下慢手，可是很危險的。'],
    hurt: ['霧被你劈開了。', '這手筋很漂亮。', '你抓到真身了。'],
    low_hp: ['霧還能再聚一次。', '別讓我拖進變化。', '最後的幻象最像正解。'],
    die: ['霧散，答案留下。', '手筋歸你。', '我在下一片林霧等你。']
  },

  tribal_orc: {
    enter: ['部落戰鼓響了。', '這不是小兵，是整支戰線。', '厚薄、攻防，全都拿出來。'],
    taunt: ['戰線破了，聽見了嗎？', '你救一邊，我就打另一邊。', '力量不是亂撞，是壓住要點。'],
    hurt: ['鼓聲亂了。', '你斷得很準。', '這下部落要重整隊形。'],
    low_hp: ['戰鼓還在響。', '最後一波衝鋒。', '只要你鬆手，我就反撲。'],
    die: ['戰鼓停了。', '部落承認你的棋力。', '勝利旗交給你。']
  },

  bounty_warlord: {
    enter: ['銀牌懸賞首領，接受討伐。', '想領賞？先拿出真本事。', '我的首級，可不是白送的。'],
    taunt: ['賞金獵人就這點眼力？', '你的攻勢缺一口氣。', '貪賞金的人，最容易被反殺。'],
    hurt: ['這刀砍得深。', '懸賞單要改價了。', '你有資格接近我。'],
    low_hp: ['賞金還沒到手。', '我還能拖你進最後陷阱。', '別在收官前露出破綻。'],
    die: ['賞金歸你。', '我的名字，從榜上劃掉吧。', '你完成討伐了。']
  },

  wyvern: {
    enter: ['飛龍掠空。抬頭，看全局。', '局部若慢，天空會先崩。', '我的影子會落在你的弱棋上。'],
    taunt: ['你只看地面，忘了天上。', '這條大龍，飛不動了吧？', '全局的風向已經變了。'],
    hurt: ['翼骨被截住了。', '你抓到我的落點。', '這手讓天空失衡。'],
    low_hp: ['我還能俯衝一次。', '最後的風壓來了。', '別讓我飛回角落。'],
    die: ['飛龍墜落。', '天空讓給你。', '你配得上更高的試煉。']
  },

  dragon_oracle: {
    enter: ['龍谷計算者展開棋卷。', '每一手，都在我的預言裡。', '想破局，就算到更深處。'],
    taunt: ['這變化，我早就看過。', '你的讀秒比龍息還短。', '少算一路，就會失去全局。'],
    hurt: ['預言出現裂痕。', '你算到了我沒算的分支。', '這手讓龍谷沉默了。'],
    low_hp: ['預言還有最後一頁。', '別急著宣判，變化還沒完。', '我會把你拖進最長的支線。'],
    die: ['預言改寫了。', '龍谷承認你的計算。', '這卷殘譜，歸你保管。']
  },

  lich_mage: {
    enter: ['亡靈賢者自塔中醒來。', '細節，就是魔法。', '半目之差，也足以讓高塔崩塌。'],
    taunt: ['你漏看的，是最致命的咒式。', '這手太凡人了。', '我會把你的薄味煉成詛咒。'],
    hurt: ['咒式被反制了。', '你的手順很乾淨。', '我感到塔基在震。'],
    low_hp: ['亡靈不會立刻消散。', '最後一道禁咒，開啟。', '你還沒走出塔影。'],
    die: ['塔燈熄滅。', '我的咒式輸給你的正著。', '賢者之名，暫借給你。']
  },

  archmage_lich: {
    enter: ['高塔術師降臨。讀不深，就別進塔。', '你的每個慢手，都會變成代價。', '高塔上沒有僥倖。'],
    taunt: ['我已經看見三手後的崩潰。', '那不是妙手，是陷阱的入口。', '別用願望代替計算。'],
    hurt: ['高塔被你撼動了。', '這手超出預估。', '你逼我重寫咒陣。'],
    low_hp: ['最後一層塔門還在。', '我會用殘局拖住你。', '別讓勝勢變成故事。'],
    die: ['高塔垂下旗幟。', '術式解除，你勝了。', '你的計算通過高塔審判。']
  },

  armored_knight: {
    enter: ['騎士披甲，請正面交鋒。', '榮耀不救壞形，只有好棋能。', '讓我看看你的戰線。'],
    taunt: ['你的陣形露出縫了。', '騎士不追幻影，只斬弱點。', '這手守不住城門。'],
    hurt: ['甲冑裂了。', '你的攻擊很有秩序。', '這一劍，我接得勉強。'],
    low_hp: ['騎士仍站著。', '最後一盾，最後一劍。', '別在勝利前失去紀律。'],
    die: ['騎士低頭致意。', '此戰，你有榮耀。', '城門為你打開。']
  },

  royal_knight: {
    enter: ['皇家騎士長奉命試煉你。', '這盤棋，將記入王城卷宗。', '拿出能配得上徽章的手。'],
    taunt: ['王城不收這種俗手。', '你的防線太散。', '榮耀前面，先補弱點。'],
    hurt: ['好劍法。', '王城盾陣被破了一角。', '你這手值得記錄。'],
    low_hp: ['騎士長不會退。', '最後的宣誓還沒結束。', '勝利前，請保持端正。'],
    die: ['王城承認你。', '此戰記入榮耀冊。', '騎士長向你行禮。']
  },

  storm_deity: {
    enter: ['風暴神靈睜眼。棋盤開始鳴雷。', '凡人的手，能否承受天雷？', '全局的雲層已經聚攏。'],
    taunt: ['雷聲會照出你的弱點。', '這手太輕，會被風捲走。', '你擋不住全局的風暴。'],
    hurt: ['雷雲被切開了。', '你竟然抓住了風眼。', '這一手讓神域震動。'],
    low_hp: ['最後一道雷還沒落下。', '風暴中心仍在我手裡。', '別被勝勢的光刺瞎。'],
    die: ['風暴散去。', '神域記下你的名字。', '雷聲為你停了。']
  },

  fate_deity: {
    enter: ['命運試煉官翻開判卷。', '你的下一手，會改寫哪條線？', '命運不偏心，只記錄正著。'],
    taunt: ['這條線通往失敗。', '你選了最脆的一枝。', '命運已經在旁邊註記了。'],
    hurt: ['判卷被改寫了。', '你走出預定軌跡。', '這手讓命運停筆。'],
    low_hp: ['最後一頁還空著。', '別急，命運喜歡反轉。', '終局前，沒有必然。'],
    die: ['判決：挑戰者勝。', '命運讓路。', '你親手寫下答案。']
  },

  ancient_idol: {
    enter: ['上古神殿甦醒。', '古老棋形，正在審視你。', '踏入神殿前，先整理你的手順。'],
    taunt: ['神殿不回應雜亂的棋。', '你的形，承受不了這座重量。', '古老答案就在眼前，你卻繞遠了。'],
    hurt: ['石像出現裂紋。', '你讀懂了古譜。', '這手讓神殿震了一下。'],
    low_hp: ['神殿核心還在。', '最後一道石門尚未倒塌。', '別在遺跡深處迷路。'],
    die: ['神殿沉默，門已開。', '上古殘卷承認你。', '石像為你讓路。']
  },

  omega_idol: {
    enter: ['終焉神降臨。這是最後的棋盤。', '你的所有練習，都會在此結算。', '落子吧，讓終焉看看你。'],
    taunt: ['終焉不接受僥倖。', '你的全局感還不夠完整。', '一步鬆，萬象崩。'],
    hurt: ['終焉裂開一道光。', '你把不可能下成了可能。', '這手有資格留下傳說。'],
    low_hp: ['最後的神諭仍未熄滅。', '別在終點前回頭。', '再一手，決定傳說或塵埃。'],
    die: ['終焉退去，傳說開始。', '你通過最後審判。', '棋盤記住了你的名字。']
  }
};

const MONSTER_TRASH_EXTRA = {
  default: {
    enter: ['黑白契約已生效，棋盤會替你說真話。'],
    taunt: ['別讓氣勢替你落子，棋盤只認計算。'],
    hurt: ['這手逼得我重新整理戰線。'],
    low_hp: ['最後一口氣，往往藏著最毒的反擊。'],
    die: ['你把這場試煉收束得很乾淨。']
  },
  slime: {
    enter: ['噗嚕噗嚕，今天也從最小的破綻開始。'],
    taunt: ['你以為我只會黏？我也會吃掉鬆手。'],
    hurt: ['這一下把我打得四散了。'],
    low_hp: ['我快散掉了，但還能再黏住一角。'],
    die: ['噗嚕，這攤經驗值歸你了。']
  },
  goblin_guard: {
    enter: ['守門規矩很簡單：數錯氣就退回去。'],
    taunt: ['門前這點破綻，我替你看見了。'],
    hurt: ['守門牌被你敲歪了。'],
    low_hp: ['只剩最後一道門閂了。'],
    die: ['通行章給你，別弄丟。']
  },
  cave_bat: {
    enter: ['洞裡的聲音會放大每一步錯棋。'],
    taunt: ['我聽見你那塊棋在喘氣。'],
    hurt: ['回聲亂了，你抓得太準。'],
    low_hp: ['我還能貼著棋盤邊緣逃一次。'],
    die: ['洞窟回音承認你贏了。']
  },
  goblin_raider: {
    enter: ['突襲隊已分兩路，看看你先救哪邊。'],
    taunt: ['你補東邊，我就搶西邊。'],
    hurt: ['兩翼都被你看住了，麻煩。'],
    low_hp: ['最後一次突襲，賭你會漏看。'],
    die: ['突襲失敗，戰利品留下。']
  },
  orc_grunt: {
    enter: ['斧頭不懂變化，但懂得劈薄棋。'],
    taunt: ['你的棋形薄得能透風。'],
    hurt: ['這手像盾，硬是擋住了我。'],
    low_hp: ['我還有一斧，別站太近。'],
    die: ['獸人倒下，戰線歸你。']
  },
  orc_shield: {
    enter: ['盾兵進場，先問你的棋有沒有眼。'],
    taunt: ['撞盾不算攻擊，只算送氣。'],
    hurt: ['盾縫被你找到，漂亮。'],
    low_hp: ['盾裂了，但還沒碎。'],
    die: ['盾牆散開，路讓給你。']
  },
  forest_spirit: {
    enter: ['森林裡沒有廢手，只有被忽略的枝節。'],
    taunt: ['你踩到的不是落葉，是斷點。'],
    hurt: ['這手像清風，穿過了林縫。'],
    low_hp: ['最後一根藤蔓還能纏住你。'],
    die: ['森林收起霧氣，讓你通行。']
  },
  mist_dryad: {
    enter: ['霧很厚，但正著只有一條路。'],
    taunt: ['你追到的是霧，不是答案。'],
    hurt: ['幻象被切開了。'],
    low_hp: ['最後一層霧最會騙人。'],
    die: ['霧林低頭，手筋歸你。']
  },
  tribal_orc: {
    enter: ['部落戰線展開，別只盯著一顆棋。'],
    taunt: ['你的戰線太長，補不完的。'],
    hurt: ['鼓點慢了半拍，你抓住了。'],
    low_hp: ['最後的戰鼓，會敲在你的弱棋上。'],
    die: ['部落退旗，今日由你領戰功。']
  },
  bounty_warlord: {
    enter: ['懸賞榜上的名字，可不是白貼的。'],
    taunt: ['想領賞？先別把自己的棋送掉。'],
    hurt: ['賞金要加碼了，這手夠狠。'],
    low_hp: ['只差一刀，但我還有陷阱。'],
    die: ['榜單劃名，賞金歸你。']
  },
  wyvern: {
    enter: ['飛龍盤旋，先看清整片天空。'],
    taunt: ['你顧著角落，天空已經丟了。'],
    hurt: ['我的俯衝路線被你封死。'],
    low_hp: ['最後一陣風，可能翻掉整盤。'],
    die: ['龍翼折落，天空安靜了。']
  },
  dragon_oracle: {
    enter: ['龍谷預言啟封，請用計算反駁我。'],
    taunt: ['這條變化的結尾，我已經讀過。'],
    hurt: ['預言被你改了一行。'],
    low_hp: ['最後一頁預言，還沒被翻完。'],
    die: ['龍谷合卷，承認你的答案。']
  },
  lich_mage: {
    enter: ['亡靈法陣亮起，慢手會變成詛咒。'],
    taunt: ['這種手順，連學徒都會皺眉。'],
    hurt: ['咒文斷了一節。'],
    low_hp: ['殘咒仍能拖住你的勝勢。'],
    die: ['塔影退去，棋盤重見光。']
  },
  archmage_lich: {
    enter: ['高塔頂端沒有僥倖，只有讀秒和真相。'],
    taunt: ['你那條變化，第三手就塌了。'],
    hurt: ['塔頂的鐘聲被你打亂了。'],
    low_hp: ['最後一層咒陣正在反轉。'],
    die: ['高塔熄燈，勝利歸檔。']
  },
  armored_knight: {
    enter: ['披甲者不怕戰鬥，只怕好棋。'],
    taunt: ['你的陣形還沒站穩。'],
    hurt: ['這一擊穿過甲縫了。'],
    low_hp: ['我還能守住最後一格。'],
    die: ['甲冑落地，騎士認輸。']
  },
  royal_knight: {
    enter: ['皇家試煉開始，請下出配得上徽章的一手。'],
    taunt: ['王城會記錄這步失誤。'],
    hurt: ['這手值得刻進戰報。'],
    low_hp: ['騎士長最後的守勢還沒撤。'],
    die: ['王城鐘響，為你記功。']
  },
  storm_deity: {
    enter: ['雷雲壓境，棋盤只剩風眼可尋。'],
    taunt: ['雷光照見了你的薄味。'],
    hurt: ['你竟斬斷了雷脈。'],
    low_hp: ['最後一道天雷，專打鬆手。'],
    die: ['風暴止息，神域退讓。']
  },
  fate_deity: {
    enter: ['命運的判卷攤開，請選你的分歧。'],
    taunt: ['這條命運線正在變黑。'],
    hurt: ['你把判詞改寫了。'],
    low_hp: ['最後一筆還沒落下。'],
    die: ['命運蓋印：挑戰者勝。']
  },
  ancient_idol: {
    enter: ['古神殿的石眼睜開，審判你的手順。'],
    taunt: ['遺跡不會回應鬆散的形。'],
    hurt: ['石紋裂開，古譜露出答案。'],
    low_hp: ['最後一道石門仍在閉合。'],
    die: ['神殿讓路，殘卷歸你。']
  },
  omega_idol: {
    enter: ['終焉之局展開，請把一路走來都放上棋盤。'],
    taunt: ['終點前的錯手，最接近深淵。'],
    hurt: ['終焉核心被你照出裂光。'],
    low_hp: ['再一手，傳說或塵埃。'],
    die: ['終焉退場，你的傳說開局。']
  }
};

Object.entries(MONSTER_TRASH_EXTRA).forEach(([monsterKey, events]) => {
  const target = _TRASH[monsterKey];
  if (!target) return;
  Object.entries(events).forEach(([eventKey, lines]) => {
    if (!target[eventKey]) target[eventKey] = [];
    target[eventKey].push(...lines);
  });
});

const MONSTER_TRASH_ALIAS = {
  caterpillar: 'slime',
  bee: 'cave_bat',
  turtle: 'orc_grunt',
  rabbit: 'forest_spirit',
  raccoon: 'tribal_orc',
  wolf: 'wyvern',
  fox: 'lich_mage',
  goblin: 'goblin_guard',
  golem: 'armored_knight',
  dragon: 'storm_deity'
};

const MONSTER_TRASH = {};
Object.keys(_TRASH).forEach(key => {
  MONSTER_TRASH[key] = _TRASH[key];
});
Object.entries(MONSTER_TRASH_ALIAS).forEach(([legacyKey, currentKey]) => {
  MONSTER_TRASH[legacyKey] = _TRASH[currentKey] || _TRASH.default;
});

// English mode deliberately uses a compact, fully localized battle script.
// This prevents Chinese dialogue from leaking through older monster packs while
// keeping every battle event (entrance, taunt, hurt, low HP and defeat) covered.
const MONSTER_TRASH_EN = {
  enter: [
    'The contract is active. Place your first stone, challenger.',
    'The board is open. Show me how you begin.',
    'No fear. Count the liberties and make your move.'
  ],
  taunt: [
    'Did you really read that move to the end?',
    'Your weakness is shining on the board.',
    'Hesitate again and I will tear open that gap.'
  ],
  hurt: [
    'That move had teeth.',
    'You found the vital liberty.',
    'Now I have to recalculate.'
  ],
  low_hp: [
    'This is not over. I still have one last breath.',
    'Do not relax before the endgame.',
    'One loose move and I can still turn this around.'
  ],
  die: [
    'This game is yours.',
    'I will remember that move.',
    'Contract complete. Next time I will be stronger.'
  ]
};

function getMonsterTrash(type) {
  if (window.I18n && I18n.getLang && I18n.getLang() === 'en') return MONSTER_TRASH_EN;
  if (!type) return MONSTER_TRASH.default;
  return MONSTER_TRASH[type] || MONSTER_TRASH[MONSTER_TRASH_ALIAS[type]] || MONSTER_TRASH.default;
}

window.MONSTER_TRASH = MONSTER_TRASH;
window.MONSTER_TRASH_ALIAS = MONSTER_TRASH_ALIAS;
window.getMonsterTrash = getMonsterTrash;
