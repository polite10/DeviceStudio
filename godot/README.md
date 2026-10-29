# ADASLab Drive — Godot 3B görünümü

Studio'nun yönettiği trafik dünyasını gerçek 3B modellerle gösteren ayrı oyun penceresi. Model/ışık/gölge/kamera ve klavye girişi Godot'ta; fizik, senaryolar ve USB bağlantısının sahibi Python Studio'dur. ACC/AEB kararları karttaki mevcut ADASLab v2 C firmware'inde hesaplanır.

## Çalıştırma

```sh
# Resmi motoru indirir, SHA512 doğrular, yalnız .tools/godot altına açar:
.venv/bin/python tools/install_godot.py
# Gerçek kart ile Studio + 3B oyun:
./Start.command --game
# Derlenmiş ARM firmware ile, fiziksel karta erişmeden:
./Start.command --game-sim
```

Windows: `./Start.ps1 --game`; bağımsız motor varsa `GODOT_BIN` yürütülebilir dosyasını gösterebilir. Kaynak projede `godot/adas_drive/project.godot` açılarak sahne düzenlenebilir. İlk açılışta modeller arka planda aktarılır; Studio kullanılabilir durumda kalır. Motor ve `.godot` önbelleği Git'e dahil edilmez.

Studio'daki **3B sürüşü aç** düğmesi de aynı pencereyi başlatır. **Sürüşü başlat** ile oyun başlar; W/↑ gaz, S/↓ fren, A–D/←→ şerit, Boşluk/Esc duraklatma, C/F kamera değişimidir. Duraklatma menüsünde destek modu, ACC, hedef hız ve trafik tohumu seçilir. Aynı tohum ve aynı sürücü girdileri aynı trafik akışını tekrarlar.

Pencere odağı kaybolunca tuşlar bırakılır ve sürüş duraklar. Studio odağını Godot'a devrederken Godot'un güncel odak bildirimi dikkate alınır. Godot kapanır/bağlantı kesilirse Studio sürüşü durdurur. Kart ekranı mevcut başlat/duraklat, mod, hedef hız ve takip süresi işlevlerini korur. Karttan başlatma için Studio veya 3B oyun penceresinin etkin olması gerekir.

Eski QML görünümü `--game-2d` veya `--game-2d-sim` ile kullanılabilir. Mevcut ADAS laboratuvarı, konsol ve firmware yükleme ekranları korunur.

## Veri akışı

Tek bir Python işçisi UART'ın sahibidir. Godot UART açmaz ve bağımsız araç fiziği yürütmez. Python yalnız karttan onaylanan ölçümden sonra fizik adımını ilerletir (50 ms). TCP sahne güncellemeleri 20 Hz; GPU çizimi ekranın yenileme hızında çalışır. Önceki ve güncel onaylı konum arasında ara kareler çizilir; son ölçümün ötesine fizik tahmini yapılmaz. 60 FPS bir performans hedefidir.

TCP sunucusu yalnız `127.0.0.1` üzerinde rastgele portta dinler. Her çalıştırma ayrı token kullanır. Tek istemci, satır başına en fazla 64 KiB, GUI turu başına sınırlı mesaj, en güncel sahneyi tutan sınırlı çıktı tamponu vardır. Motor 100 ms'de bir odak/yaşam bildirimi gönderir; 350 ms'den eski istemci düşürülür ve sürüş durdurulur.

Satır sonlu JSON protokolü:

```json
{"type":"hello","protocol":1,"token":"oturuma-özel"}
{"type":"heartbeat","active":true}
{"type":"input","key":"w","pressed":true,"repeat":false}
{"type":"action","name":"pause"}
{"type":"setting","key":"mode","value":"warn"}
```

Studio: `{"type":"state","protocol":1,"state":{...},"connected":true,"backend":"STM32_UART"}`. `ARM_SIM` gerçek derlenmiş firmware kodunu Unicorn'da çalıştırır. `--demo` yalnız görsel kontrol için ayrı bir örnek trafik üretir ve ekranda açıkça DEMO olarak gösterilir.

## Grafikler ve kaynaklar

Gerçek üç boyutlu araç modelleri, ayrı tekerlekler ve fren lambaları; arka takip/kaput kameraları; ışık, gölge, sis, çevre ve asfalt/şerit geometrisi kullanılır. Varlıklar Quaternius ve Kenney'nin CC0 modelleridir. Lisans, kaynak URL'leri ve bütünlük değerleri [assets/ATTRIBUTION.md](adas_drive/assets/ATTRIBUTION.md) ve [assets/sources.json](adas_drive/assets/sources.json) içindedir.

Bu sahne bir eğitim simülasyonudur. Görsel süspansiyon/tekerlek hareketleri araç dinamiği doğrulaması yerine geçmez; fiziksel sensör veya görüntü işleme eklenmemiştir.

## Doğrulama

2026-10-29: 99 Python/birim testi, 58 korunmuş QML oyun kontrolü, 16 yenileme etkileşimi ve QML lint geçti. Gerçek Godot işlemiyle ARM simülasyonunda 27 motor kontrolü + 12 host kontrolü; fiziksel ADASLab v2 kartıyla native Metal görünümünde 31 motor kontrolü + 12 host kontrolü geçti. Modlar, bağımsız gaz tuşları, şerit/fren, ayar taslağı/imleç, odak kaybı, kamera değişimi ve motor kapanışında MCU PAUSE doğrulandı. Son native örnekte 60 FPS ölçüldü. Ayrıntılar [godot-verification.json](../godot-verification.json) içinde.

```sh
# Önce import (normal Studio açılışı bunu arka planda yapar):
.tools/godot/Godot.app/Contents/MacOS/Godot --headless --editor --path godot/adas_drive --import --quit
# Kart olmadan gerçek motor + ARM ELF:
.venv/bin/python tools/verify_godot_session.py
# Önceden ADASLab v2 yüklenmiş gerçek kart + native 3B pencere:
.venv/bin/python tools/verify_godot_session.py --visible --backend hardware --port /dev/cu.usbmodem11403 --output-dir build/godot-hardware-qa
```

Portu kendi cihazınıza göre değiştirin; önce açık Studio bağlantısını kapatın. Testler Flash'a yazmaz. Godot tuş testleri normal motor girdi hattına sentetik olay gönderir; fiziksel klavye/parmak otomasyonu değildir. Windows/Linux üzerinde native grafik çalıştırması yapılmadı.

![Gerçek kartla 3B sürüş ve AEB](../docs/adaslab-drive-3d.png)
