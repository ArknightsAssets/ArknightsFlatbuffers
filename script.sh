# generate arknights flatbuffers schema by bruteforcing previously-known schemas

TMP="/tmp/fbs-tw"
rm -rf $TMP ||:
mkdir -p $TMP

rm -rf cn yostar tw output

# download files, see https://github.com/ArknightsAssets/ArknightsAssets for reference
BUNDLES="$TMP/bundles"

network_config_url="https://ak-conf-tw.gryphline.com/config/prod/official/network_config";
network_config=$(curl -s "$network_config_url" | jq -r ".content")
network_urls=$(echo $network_config | jq -r ".configs[$(echo $network_config | jq ".funcVer")].network")
version_url=$(echo $network_urls | jq -r ".hv" | sed "s/{0}/Android/g")
res_version=$(curl -s "$version_url" | jq -r ".resVersion")
assets_url="$(echo $network_urls | jq -r ".hu")/Android/assets/${res_version}"

mkdir -p "$BUNDLES"

while IFS="," read -r path hash; do
    if [[ ${path} =~ gamedata|anon ]]; then
        formatted_path=$(echo "$path" | sed -e "s|/|_|g" -e "s|#|__|" -e "s|\..*|.dat|g")
        wget -q -c -P "/tmp/akassets" "${assets_url}/${formatted_path}"
        unzip -q -o "/tmp/akassets/${formatted_path}" -d "$BUNDLES"
        rm "/tmp/akassets/${formatted_path}"
        echo "${path}"
    fi
done < <(curl -s "${assets_url}/hot_update_list.json" | jq -r -c '.abInfos[] | "\(.name),\(.hash)"')
wait

# download pre-requisites
wget -q -c -O "$TMP/ArknightsStudioCLI.zip" "https://github.com/thesadru/AssetStudio/releases/download/ak-v1.2.1/ArknightsStudioCLI-net6-linux64.v1.2.1.zip"
unzip -q -d "$TMP/ArknightsStudioCLI" "$TMP/ArknightsStudioCLI.zip"
chmod +x $TMP/ArknightsStudioCLI/ArknightsStudioCLI

wget -q -c -O "$TMP/flatc.zip" "https://github.com/google/flatbuffers/releases/download/v24.3.25/Linux.flatc.binary.g++-13.zip"
unzip -q -d "$TMP" "$TMP/flatc.zip"
chmod +x $TMP/flatc

OAFBS=$TMP/OpenArknightsFBS
git clone https://github.com/MooncellWiki/OpenArknightsFBS $OAFBS

# go through downloaded files and try to parse them with flatc
$TMP/ArknightsStudioCLI/ArknightsStudioCLI "$BUNDLES" -t TextAsset -o "$TMP/extracted"

mkdir -p "$TMP/export"
mkdir -p "$TMP/extracted-cut"
mkdir -p "$TMP/fb"
mkdir -p "tw"
mkdir -p "output/tw"
mkdir -p "output/tw/levels"
for path in $(find "$TMP/extracted/assets/torappu/dynamicassets/gamedata" -type f -name "*.bytes"); do
    cutpath="$TMP/extracted-cut/$(basename $path)"
    dd if=$path bs=128 skip=1 of=$cutpath 2>/dev/null

    if [[ $path =~ gamedata/(.+_(table|data|const|database))([0-9a-fA-F]{6}) ]]; then
        name=$(basename "${BASH_REMATCH[1]}")

        git -C $OAFBS rev-list --all --objects -- FBS/$name.fbs | cut -d ' ' -f1 |
        while read h; do
            git -C $OAFBS cat-file -p ${h}:FBS/$name.fbs > $TMP/export/$name.$h.fbs;
            $TMP/flatc -o "output/tw" "$TMP/export/$name.$h.fbs" -- "$cutpath" --no-warnings --json --strict-json --natural-utf8 --defaults-json --unknown-json --raw-binary --force-empty 1> /dev/null 2> /dev/null
            if [[ $? == 0 ]]; then
                mv "output/tw/$(basename $cutpath .bytes).json" "output/tw/$name.json"
                echo "// https://github.com/MooncellWiki/OpenArknightsFBS/commit/$h" | cat - $TMP/export/$name.$h.fbs > tw/$name.fbs
                echo $name - $h
                break
            fi
        done    
    fi
done

name=prts___levels
git -C $OAFBS rev-list --all --objects -- FBS/$name.fbs | cut -d ' ' -f1 |
while read h; do
    success=1

    git -C $OAFBS cat-file -p ${h}:FBS/$name.fbs > $TMP/export/$name.$h.fbs;
    # maybe it will work, maybe it won't. Who can tell?
    for path in $(find "$TMP/extracted/assets/torappu/dynamicassets/gamedata/levels/activities" -type f -name "*.bytes" | shuf -n 20); do
        cutpath="$TMP/extracted-cut/$(basename $path)"
        dd if=$path bs=128 skip=1 of=$cutpath 2>/dev/null

        echo "$h $path"
        $TMP/flatc -o "output/tw/levels" "$TMP/export/$name.$h.fbs" -- "$cutpath" --no-warnings --json --strict-json --natural-utf8 --defaults-json --unknown-json --raw-binary --force-empty 1> /dev/null 2> /dev/null
        if [[ $? != 0 ]]; then
            success=0
            break
        fi
    done
    if [[ $success == 1 ]]; then
        echo "// https://github.com/MooncellWiki/OpenArknightsFBS/commit/$h" | cat - $TMP/export/$name.$h.fbs > tw/$name.fbs
        break
    fi
done;

git -C $OAFBS checkout origin/main
cp -r $TMP/OpenArknightsFBS/FBS cn
git -C $OAFBS checkout origin/YoStar
# cp -r $TMP/OpenArknightsFBS/FBS yostar
cp -r $TMP/OpenArknightsFBS/FBS yostar-preferred


# ===========================================================================
# yostar: generate arknights flatbuffers schema by bruteforcing previously-known schemas, but take the current schema as authority


TMP="/tmp/fbs-yostar"
rm -rf $TMP ||:
mkdir -p $TMP

# download files, see https://github.com/ArknightsAssets/ArknightsAssets for reference
BUNDLES="$TMP/bundles"

network_config_url="https://ak-conf.arknights.jp/config/prod/official/network_config"; # jp because it's earlier than en
network_config=$(curl -s "$network_config_url" | jq -r ".content")
network_urls=$(echo $network_config | jq -r ".configs[$(echo $network_config | jq ".funcVer")].network")
version_url=$(echo $network_urls | jq -r ".hv" | sed "s/{0}/Android/g")
res_version=$(curl -s "$version_url" | jq -r ".resVersion")
assets_url="$(echo $network_urls | jq -r ".hu")/Android/assets/${res_version}"

mkdir -p "$BUNDLES"

while IFS="," read -r path hash; do
    if [[ ${path} =~ gamedata|anon ]]; then
        formatted_path=$(echo "$path" | sed -e "s|/|_|g" -e "s|#|__|" -e "s|\..*|.dat|g")
        wget -q -c -P "/tmp/akassets" "${assets_url}/${formatted_path}"
        unzip -q -o "/tmp/akassets/${formatted_path}" -d "$BUNDLES"
        rm "/tmp/akassets/${formatted_path}"
        echo "${path}"
    fi
done < <(curl -s "${assets_url}/hot_update_list.json" | jq -r -c '.abInfos[] | "\(.name),\(.hash)"')
wait

# download pre-requisites
wget -q -c -O "$TMP/ArknightsStudioCLI.zip" "https://github.com/thesadru/AssetStudio/releases/download/ak-v1.2.1/ArknightsStudioCLI-net6-linux64.v1.2.1.zip"
unzip -q -d "$TMP/ArknightsStudioCLI" "$TMP/ArknightsStudioCLI.zip"
chmod +x $TMP/ArknightsStudioCLI/ArknightsStudioCLI

wget -q -c -O "$TMP/flatc.zip" "https://github.com/google/flatbuffers/releases/download/v24.3.25/Linux.flatc.binary.g++-13.zip"
unzip -q -d "$TMP" "$TMP/flatc.zip"
chmod +x $TMP/flatc

OAFBS=$TMP/OpenArknightsFBS
git clone https://github.com/MooncellWiki/OpenArknightsFBS $OAFBS

# go through downloaded files and try to parse them with flatc
$TMP/ArknightsStudioCLI/ArknightsStudioCLI "$BUNDLES" -t TextAsset -o "$TMP/extracted"

mkdir -p "$TMP/export"
mkdir -p "$TMP/extracted-cut"
mkdir -p "$TMP/fb"
mkdir -p "yostar"
mkdir -p "output/yostar"
mkdir -p "output/yostar/levels"
for path in $(find "$TMP/extracted/assets/torappu/dynamicassets/gamedata" -type f -name "*.bytes"); do
    cutpath="$TMP/extracted-cut/$(basename $path)"
    dd if=$path bs=128 skip=1 of=$cutpath 2>/dev/null

    if [[ $path =~ gamedata/(.+_(table|data|const|database))([0-9a-fA-F]{6}) ]]; then
        name=$(basename "${BASH_REMATCH[1]}")
        $TMP/flatc -o "output/yostar" "yostar-preferred/$name.fbs" -- "$cutpath" --no-warnings --json --strict-json --natural-utf8 --defaults-json --unknown-json --raw-binary --force-empty 1> /dev/null 2> /dev/null
        if [[ $? == 0 ]]; then
            mv "output/yostar/$(basename $cutpath .bytes).json" "output/yostar/$name.json"
            cp "yostar-preferred/$name.fbs" yostar/$name.fbs
            echo $name - default
            continue
        fi

        git -C $OAFBS rev-list --all --objects -- FBS/$name.fbs | cut -d ' ' -f1 |
        while read h; do
            git -C $OAFBS cat-file -p ${h}:FBS/$name.fbs > $TMP/export/$name.$h.fbs;
            $TMP/flatc -o "output/yostar" "$TMP/export/$name.$h.fbs" -- "$cutpath" --no-warnings --json --strict-json --natural-utf8 --defaults-json --unknown-json --raw-binary --force-empty 1> /dev/null 2> /dev/null
            if [[ $? == 0 ]]; then
                mv "output/yostar/$(basename $cutpath .bytes).json" "output/yostar/$name.json"
                echo "// https://github.com/MooncellWiki/OpenArknightsFBS/commit/$h" | cat - $TMP/export/$name.$h.fbs > yostar/$name.fbs
                echo $name - $h
                break
            fi
        done    
    fi
done

# todo: yostar levels
cp yostar-preferred/prts___levels.fbs yostar/prts___levels.fbs

rm -r yostar-preferred
