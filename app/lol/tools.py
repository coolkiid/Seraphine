import time
import win32gui
import win32con
import win32api
import ctypes

import qasync
import asyncio
from PyQt5.QtCore import QObject
from PyQt5.QtWidgets import QApplication

from ..common.config import cfg, Language
from ..lol.connector import LolClientConnector, connector


class ToolsTranslator(QObject):
    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.top = self.tr("TOP")
        self.jungle = self.tr("JUG")
        self.middle = self.tr("MID")
        self.bottom = self.tr("BOT")
        self.support = self.tr("SUP")

        self.rankedSolo = self.tr('Ranked Solo')
        self.rankedFlex = self.tr("Ranked Flex")


def translateTier(orig: str, short=False) -> str:
    if orig == '':
        return "--"

    maps = {
        'Iron': ['坚韧黑铁', '黑铁'],
        'Bronze': ['英勇黄铜', '黄铜'],
        'Silver': ['不屈白银', '白银'],
        'Gold': ['荣耀黄金', '黄金'],
        'Platinum': ['华贵铂金', '铂金'],
        'Emerald': ['流光翡翠', '翡翠'],
        'Diamond': ['璀璨钻石', '钻石'],
        'Master': ['超凡大师', '大师'],
        'Grandmaster': ['傲世宗师', '宗师'],
        'Challenger': ['最强王者', '王者'],
    }

    index = 1 if short else 0

    if cfg.language.value == Language.ENGLISH:
        return orig.capitalize()
    else:
        return maps[orig.capitalize()][index]


def timeStampToStr(stamp):
    """
    @param stamp: Millisecond timestamp
    """
    timeArray = time.localtime(stamp / 1000)
    return time.strftime("%Y/%m/%d %H:%M", timeArray)


def timeStampToShortStr(stamp):
    timeArray = time.localtime(stamp / 1000)
    return time.strftime("%m/%d", timeArray)


def secsToStr(secs):
    return time.strftime("%M:%S", time.gmtime(secs))


async def getRecentTeammates(games, puuid):
    summoners = {}

    for game in games:
        gameId = game['gameId']
        game = await connector.getGameDetailByGameId(gameId)
        teammates = getTeammates(game, puuid)

        for p in teammates['summoners']:
            if p['summonerId'] == 0:
                continue

            if p['puuid'] not in summoners:
                summonerIcon = await connector.getProfileIcon(p['icon'])
                summoners[p['puuid']] = {
                    "name": p['name'], 'icon': summonerIcon,
                    "total": 0, "wins": 0, "losses": 0, "puuid": p["puuid"]}

            summoners[p['puuid']]['total'] += 1

            if not teammates['remake']:
                if teammates['win']:
                    summoners[p['puuid']]['wins'] += 1
                else:
                    summoners[p['puuid']]['losses'] += 1

    ret = {"puuid": puuid, "summoners": [
        item for item in summoners.values()]}

    ret['summoners'] = sorted(ret['summoners'],
                              key=lambda x: x['total'], reverse=True)[:5]

    return ret


async def parseSummonerData(summoner):
    iconId = summoner['profileIconId']
    icon = await connector.getProfileIcon(iconId)
    level = summoner['summonerLevel']
    xpSinceLastLevel = summoner['xpSinceLastLevel']
    xpUntilNextLevel = summoner['xpUntilNextLevel']
    rankInfo = await connector.getRankedStatsByPuuid(summoner['puuid'])

    try:
        gamesInfo = await connector.getSummonerGamesByPuuid(
            summoner['puuid'], 0, cfg.get(cfg.careerGamesNumber) - 1)
    except:
        champions = []
        games = {}
    else:
        games = {
            "gameCount": gamesInfo["gameCount"],
            "wins": 0,
            "losses": 0,
            "kills": 0,
            "deaths": 0,
            "assists": 0,
            "games": [],
        }
        for game in gamesInfo["games"]:
            info = await parseGameData(game)
            if time.time() - info["timeStamp"] / 1000 > 60 * 60 * 24 * 365:
                continue
            if not info["remake"] and info["queueId"] != 0:
                games["kills"] += info["kills"]
                games["deaths"] += info["deaths"]
                games["assists"] += info["assists"]
                if info["win"]:
                    games["wins"] += 1
                else:
                    games["losses"] += 1
            games["games"].append(info)

        champions = getRecentChampions(games['games'])

    return {
        'name': summoner.get("gameName") or summoner['displayName'],
        'icon': icon,
        'level': level,
        'xpSinceLastLevel': xpSinceLastLevel,
        'xpUntilNextLevel': xpUntilNextLevel,
        'puuid': summoner['puuid'],
        'rankInfo': rankInfo,
        'games': games,
        'champions': champions,
        'isPublic': summoner['privacy'] == "PUBLIC",
        'tagLine': summoner.get("tagLine"),
    }


async def parseGameData(game):
    timeStamp = game["gameCreation"]  # 毫秒级时间戳
    time = timeStampToStr(game['gameCreation'])
    shortTime = timeStampToShortStr(game['gameCreation'])
    gameId = game['gameId']
    duration = secsToStr(game['gameDuration'])
    queueId = game['queueId']

    nameAndMap = connector.manager.getNameMapByQueueId(queueId)
    modeName = nameAndMap['name']

    if queueId != 0:
        mapName = nameAndMap['map']
    else:
        mapName = connector.manager.getMapNameById(game['mapId'])

    participant = game['participants'][0]
    championId = participant['championId']
    championIcon = await connector.getChampionIcon(championId)
    spell1Id = participant['spell1Id']
    spell2Id = participant['spell2Id']
    spell1Icon = await connector.getSummonerSpellIcon(spell1Id)
    spell2Icon = await connector.getSummonerSpellIcon(spell2Id)
    stats = participant['stats']

    champLevel = stats['champLevel']
    kills = stats['kills']
    deaths = stats['deaths']
    assists = stats['assists']
    itemIds = [
        stats['item0'],
        stats['item1'],
        stats['item2'],
        stats['item3'],
        stats['item4'],
        stats['item5'],
        stats['item6'],
    ]

    itemIcons = [await connector.getItemIcon(itemId) for itemId in itemIds]
    runeId = stats['perk0']
    runeIcon = await connector.getRuneIcon(runeId)

    cs = stats['totalMinionsKilled'] + stats['neutralMinionsKilled']
    gold = stats['goldEarned']
    remake = stats['gameEndedInEarlySurrender']
    win = stats['win']

    timeline = participant['timeline']
    lane = timeline['lane']
    role = timeline['role']

    position = None

    pt = ToolsTranslator()

    if queueId in [420, 440]:
        if lane == 'TOP':
            position = pt.top
        elif lane == "JUNGLE":
            position = pt.jungle
        elif lane == 'MIDDLE':
            position = pt.middle
        elif role == 'SUPPORT':
            position = pt.support
        elif lane == 'BOTTOM' and role == 'CARRY':
            position = pt.bottom

    return {
        'queueId': queueId,
        'gameId': gameId,
        'time': time,
        'shortTime': shortTime,
        'name': modeName,
        'map': mapName,
        'duration': duration,
        'remake': remake,
        'win': win,
        'championId': championId,
        'championIcon': championIcon,
        'spell1Icon': spell1Icon,
        'spell2Icon': spell2Icon,
        'champLevel': champLevel,
        'kills': kills,
        'deaths': deaths,
        'assists': assists,
        'itemIcons': itemIcons,
        'runeIcon': runeIcon,
        'cs': cs,
        'gold': gold,
        'timeStamp': timeStamp,
        'position': position,
    }


async def parseGameDetailData(puuid, game):
    queueId = game['queueId']
    mapId = game['mapId']

    names = connector.manager.getNameMapByQueueId(queueId)
    modeName = names['name']
    if queueId != 0:
        mapName = names['map']
    else:
        mapName = connector.manager.getMapNameById(mapId)

    def origTeam(teamId):
        return {
            'win': None,
            'bans': [],
            'baronKills': 0,
            'baronIcon': f"app/resource/images/baron-{teamId}.png",
            'dragonKills': 0,
            'dragonIcon': f'app/resource/images/dragon-{teamId}.png',
            'riftHeraldKills': 0,
            'riftHeraldIcon': f'app/resource/images/herald-{teamId}.png',
            'inhibitorKills': 0,
            'inhibitorIcon': f'app/resource/images/inhibitor-{teamId}.png',
            'towerKills': 0,
            'towerIcon': f'app/resource/images/tower-{teamId}.png',
            'kills': 0,
            'deaths': 0,
            'assists': 0,
            'gold': 0,
            'summoners': []
        }

    teams = {
        100: origTeam("100"),
        200: origTeam("200"),
        300: origTeam("100"),
        400: origTeam("200")
    }

    cherryResult = None

    for team in game['teams']:
        teamId = team['teamId']

        if teamId == 0:
            teamId = 200

        teams[teamId]['win'] = team['win']
        teams[teamId]['bans'] = [
            await connector.getChampionIcon(item['championId'])
            for item in team['bans']
        ]
        teams[teamId]['baronKills'] = team['baronKills']
        teams[teamId]['dragonKills'] = team['dragonKills']
        teams[teamId]['riftHeraldKills'] = team['riftHeraldKills']
        teams[teamId]['towerKills'] = team['towerKills']
        teams[teamId]['inhibitorKills'] = team['inhibitorKills']

    for participant in game['participantIdentities']:
        participantId = participant['participantId']
        summonerName = participant['player'].get(
            'gameName') or participant['player'].get('summonerName')  # 兼容外服
        summonerPuuid = participant['player']['puuid']
        isCurrent = (summonerPuuid == puuid)

        if summonerPuuid == '00000000-0000-0000-0000-000000000000':  # AI
            isPublic = True
        else:
            t = await connector.getSummonerByPuuid(summonerPuuid)
            isPublic = t["privacy"] == "PUBLIC"

        for summoner in game['participants']:
            if summoner['participantId'] == participantId:
                stats = summoner['stats']

                if queueId != 1700:
                    subteamPlacement = None
                    tid = summoner['teamId']
                else:
                    subteamPlacement = stats['subteamPlacement']
                    tid = subteamPlacement * 100

                if isCurrent:
                    remake = stats['gameEndedInEarlySurrender']
                    win = stats['win']

                    if queueId == 1700:
                        cherryResult = subteamPlacement

                championId = summoner['championId']
                championIcon = await connector.getChampionIcon(championId)

                spell1Id = summoner['spell1Id']
                spell1Icon = await connector.getSummonerSpellIcon(spell1Id)
                spell2Id = summoner['spell2Id']
                spell2Icon = await connector.getSummonerSpellIcon(spell2Id)

                kills = stats['kills']
                deaths = stats['deaths']
                assists = stats['assists']
                gold = stats['goldEarned']

                teams[tid]['kills'] += kills
                teams[tid]['deaths'] += deaths
                teams[tid]['assists'] += assists
                teams[tid]['gold'] += gold

                runeIcon = await connector.getRuneIcon(stats['perk0'])

                itemIds = [
                    stats['item0'],
                    stats['item1'],
                    stats['item2'],
                    stats['item3'],
                    stats['item4'],
                    stats['item5'],
                    stats['item6'],
                ]

                itemIcons = [
                    await connector.getItemIcon(itemId) for itemId in itemIds
                ]

                getRankInfo = cfg.get(cfg.showTierInGameInfo)

                tier, division, lp, rankIcon = None, None, None, None
                if getRankInfo:
                    rank = await connector.getRankedStatsByPuuid(
                        summonerPuuid)
                    rank = rank.get('queueMap')

                    try:
                        if queueId != 1700 and rank:
                            rankInfo = rank[
                                'RANKED_FLEX_SR'] if queueId == 440 else rank['RANKED_SOLO_5x5']

                            tier = rankInfo['tier']
                            division = rankInfo['division']
                            lp = rankInfo['leaguePoints']

                            if tier == '':
                                rankIcon = 'app/resource/images/unranked.png'
                            else:
                                rankIcon = f'app/resource/images/{tier.lower()}.png'
                                tier = translateTier(tier, True)

                            if division == 'NA':
                                division = ''
                        else:
                            rankInfo = rank["CHERRY"]
                            lp = rankInfo['ratedRating']
                    except KeyError:
                        ...

                item = {
                    'summonerName': summonerName,
                    'puuid': summonerPuuid,
                    'isCurrent': isCurrent,
                    'championIcon': championIcon,
                    'rankInfo': getRankInfo,
                    'tier': tier,
                    'division': division,
                    'lp': lp,
                    'rankIcon': rankIcon,
                    'spell1Icon': spell1Icon,
                    'spell2Icon': spell2Icon,
                    'itemIcons': itemIcons,
                    'kills': kills,
                    'deaths': deaths,
                    'assists': assists,
                    'cs': stats['totalMinionsKilled'] + stats['neutralMinionsKilled'],
                    'gold': gold,
                    'runeIcon': runeIcon,
                    'champLevel': stats['champLevel'],
                    'demage': stats['totalDamageDealtToChampions'],
                    'subteamPlacement': subteamPlacement,
                    'isPublic': isPublic
                }
                teams[tid]['summoners'].append(item)

                break

    mapIcon = connector.manager.getMapIconByMapId(mapId, win)

    return {
        'gameId': game['gameId'],
        'mapIcon': mapIcon,
        'gameCreation': timeStampToStr(game['gameCreation']),
        'gameDuration': secsToStr(game['gameDuration']),
        'modeName': modeName,
        'mapName': mapName,
        'queueId': queueId,
        'win': win,
        'cherryResult': cherryResult,
        'remake': remake,
        'teams': teams,
    }


def getTeammates(game, targetPuuid):
    """
    通过 game 信息获取目标召唤师的队友

    @param game: @see connector.getGameDetailByGameId
    @param targetPuuid: 目标召唤师 puuid
    @return: @see res
    """
    targetParticipantId = None

    for participant in game['participantIdentities']:
        puuid = participant['player']['puuid']

        if puuid == targetPuuid:
            targetParticipantId = participant['participantId']
            break

    assert targetParticipantId is not None

    for player in game['participants']:
        if player['participantId'] == targetParticipantId:
            if game['queueId'] != 1700:
                tid = player['teamId']
            else:  # 斗魂竞技场
                tid = player['stats']['subteamPlacement']

            win = player['stats']['win']
            remake = player['stats']['teamEarlySurrendered']

            break

    res = {
        'queueId': game['queueId'],
        'win': win,
        'remake': remake,
        'summoners': [],  # 队友召唤师 (由于兼容性, 未修改字段名)
        'enemies': []  # 对面召唤师, 若有多个队伍会全放这里面
    }

    for player in game['participants']:

        if game['queueId'] != 1700:
            cmp = player['teamId']
        else:
            cmp = player['stats']['subteamPlacement']

        p = player['participantId']
        s = game['participantIdentities'][p - 1]['player']

        if cmp == tid:
            if s['puuid'] != targetPuuid:
                res['summoners'].append(
                    {'summonerId': s['summonerId'], 'name': s['summonerName'], 'puuid': s['puuid'], 'icon': s['profileIcon']})
            else:
                # 当前召唤师在该对局使用的英雄, 自定义对局没有该字段
                res["championId"] = player.get('championId', -1)
        else:
            res['enemies'].append(
                {'summonerId': s['summonerId'], 'name': s['summonerName'], 'puuid': s['puuid'],
                 'icon': s['profileIcon']})

    return res


def getRecentChampions(games):
    champions = {}

    for game in games:
        if game['queueId'] == 0:
            continue

        championId = game['championId']

        if championId not in champions:
            champions[championId] = {
                'icon': game['championIcon'], 'wins': 0, 'losses': 0, 'total': 0}

        champions[championId]['total'] += 1

        if not game['remake']:
            if game['win']:
                champions[championId]['wins'] += 1
            else:
                champions[championId]['losses'] += 1

    ret = [item for item in champions.values()]
    ret.sort(key=lambda x: x['total'], reverse=True)

    maxLen = 10

    return ret if len(ret) < maxLen else ret[:maxLen]


def parseRankInfo(info):
    soloRankInfo = info["queueMap"]["RANKED_SOLO_5x5"]
    flexRankInfo = info["queueMap"]["RANKED_FLEX_SR"]

    soloTier = soloRankInfo["tier"]
    soloDivision = soloRankInfo["division"]

    if soloTier == "":
        soloIcon = "app/resource/images/UNRANKED.svg"
        soloTier = "Unranked" if cfg.language.value == Language.ENGLISH else "未定级"
    else:
        soloIcon = f"app/resource/images/{soloTier}.svg"
        soloTier = translateTier(soloTier, True)
    if soloDivision == "NA":
        soloDivision = ""

    flexTier = flexRankInfo["tier"]
    flexDivision = flexRankInfo["division"]

    if flexTier == "":
        flexIcon = "app/resource/images/UNRANKED.svg"
        flexTier = "Unranked" if cfg.language.value == Language.ENGLISH else "未定级"
    else:
        flexIcon = f"app/resource/images/{flexTier}.svg"
        flexTier = translateTier(flexTier, True)
    if flexDivision == "NA":
        flexDivision = ""

    return {
        "solo": {
            "tier": soloTier,
            "icon": soloIcon,
            "division": soloDivision,
            "lp": soloRankInfo["leaguePoints"],
        },
        "flex": {
            "tier": flexTier,
            "icon": flexIcon,
            "division": flexDivision,
            "lp": flexRankInfo["leaguePoints"],
        },
    }


def parseDetailRankInfo(rankInfo):
    soloRankInfo = rankInfo['queueMap']['RANKED_SOLO_5x5']
    soloTier = translateTier(soloRankInfo['tier'])
    soloDivision = soloRankInfo['division']
    if soloTier == '--' or soloDivision == 'NA':
        soloDivision = ""

    soloHighestTier = translateTier(soloRankInfo['highestTier'])
    soloHighestDivision = soloRankInfo['highestDivision']
    if soloHighestTier == '--' or soloHighestDivision == 'NA':
        soloHighestDivision = ""

    solxPreviousSeasonEndTier = translateTier(
        soloRankInfo['previousSeasonEndTier'])
    soloPreviousSeasonDivision = soloRankInfo[
        'previousSeasonEndDivision']
    if solxPreviousSeasonEndTier == '--' or soloPreviousSeasonDivision == 'NA':
        soloPreviousSeasonDivision = ""

    soloWins = soloRankInfo['wins']
    soloLosses = soloRankInfo['losses']
    soloTotal = soloWins + soloLosses
    soloWinRate = soloWins * 100 // soloTotal if soloTotal != 0 else 0
    soloLp = soloRankInfo['leaguePoints']

    flexRankInfo = rankInfo['queueMap']['RANKED_FLEX_SR']
    flexTier = translateTier(flexRankInfo['tier'])
    flexDivision = flexRankInfo['division']
    if flexTier == '--' or flexDivision == 'NA':
        flexDivision = ""

    flexHighestTier = translateTier(flexRankInfo['highestTier'])
    flexHighestDivision = flexRankInfo['highestDivision']
    if flexHighestTier == '--' or flexHighestDivision == 'NA':
        flexHighestDivision = ""

    flexPreviousSeasonEndTier = translateTier(
        flexRankInfo['previousSeasonEndTier'])
    flexPreviousSeasonEndDivision = flexRankInfo[
        'previousSeasonEndDivision']

    if flexPreviousSeasonEndTier == '--' or flexPreviousSeasonEndDivision == 'NA':
        flexPreviousSeasonEndDivision = ""

    flexWins = flexRankInfo['wins']
    flexLosses = flexRankInfo['losses']
    flexTotal = flexWins + flexLosses
    flexWinRate = flexWins * 100 // flexTotal if flexTotal != 0 else 0
    flexLp = flexRankInfo['leaguePoints']

    t = ToolsTranslator()

    return [
        [
            t.rankedSolo,
            str(soloTotal),
            str(soloWinRate) + ' %' if soloTotal != 0 else '--',
            str(soloWins),
            str(soloLosses),
            f'{soloTier} {soloDivision}',
            str(soloLp),
            f'{soloHighestTier} {soloHighestDivision}',
            f'{solxPreviousSeasonEndTier} {soloPreviousSeasonDivision}',
        ],
        [
            t.rankedFlex,
            str(flexTotal),
            str(flexWinRate) + ' %' if flexTotal != 0 else '--',
            str(flexWins),
            str(flexLosses),
            f'{flexTier} {flexDivision}',
            str(flexLp),
            f'{flexHighestTier} {flexHighestDivision}',
            f'{flexPreviousSeasonEndTier} {flexPreviousSeasonEndDivision}',
        ],
    ]


def parseGames(games, targetId=0):
    f"""
    解析Games数据

    @param targetId: 需要查询的游戏模式, 不传则收集所有模式的数据
    @param games: 由 @see: {parseGameData} 获取到的games数据
    @return: hitGame, K, D, A, win, loss
    @rtype: tuple[list, int, int, int, int, int, int]
    """

    kills, deaths, assists, wins, losses = 0, 0, 0, 0, 0
    hitGames = []

    for game in games:
        if not targetId or game['queueId'] == targetId:
            hitGames.append(game)

            if not game['remake']:
                kills += game['kills']
                deaths += game['deaths']
                assists += game['assists']

                if game['win']:
                    wins += 1
                else:
                    losses += 1

    return hitGames, kills, deaths, assists, wins, losses


async def parseAllyGameInfo(session, currentSummonerId):
    # 排位会有预选位
    isRank = bool(session["myTeam"][0]["assignedPosition"])

    tasks = [parseSummonerGameInfo(item, isRank, currentSummonerId)
             for item in session['myTeam']]
    summoners = await asyncio.gather(*tasks)
    summoners = [summoner for summoner in summoners if summoner]

    # 按照楼层排序
    summoners = sorted(
        summoners, key=lambda x: x["cellId"])

    champions = {summoner['summonerId']: summoner['championId']
                 for summoner in summoners}
    order = [summoner['summonerId'] for summoner in summoners]

    return {'summoners': summoners, 'champions': champions, 'order': order}


def parseSummonerOrder(team):
    summoners = [{
        'summonerId': s['summonerId'],
        'cellId': s['cellId']
    } for s in team]

    summoners.sort(key=lambda x: x['cellId'])
    return [s['summonerId'] for s in summoners if s['summonerId'] != 0]


async def parseGameInfoByGameflowSession(session, currentSummonerId, side):
    data = session['gameData']
    queueId = data['queue']['id']

    if queueId in (1700, 1090, 1100, 1110, 1130, 1160):  # 斗魂 云顶匹配 (排位)
        return None

    isRank = queueId in (420, 440)

    if side == 'enemy':
        _, team = separateTeams(data, currentSummonerId)
    else:
        team, _ = separateTeams(data, currentSummonerId)

    tasks = [parseSummonerGameInfo(item, isRank, currentSummonerId)
             for item in team]

    summoners = await asyncio.gather(*tasks)
    summoners = [summoner for summoner in summoners if summoner]

    if isRank:
        s = sortedSummonersByGameRole(summoners)

        if s != None:
            summoners = s

    champions = {summoner['summonerId']: summoner['championId']
                 for summoner in summoners}
    order = [summoner['summonerId'] for summoner in summoners]

    return {'summoners': summoners, 'champions': champions, 'order': order}


def sortedSummonersByGameRole(summoners: list):
    position = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]

    if any(x['selectedPosition'] not in position for x in summoners):
        return None

    return sorted(summoners,
                  key=lambda x: position.index(x['selectedPosition']))


def getAllyOrderByGameRole(session, currentSummonerId):
    data = session['gameData']
    queueId = data['queue']['id']

    # 只有排位模式下有返回值
    if queueId not in (420, 440):
        return None

    ally, _ = separateTeams(data, currentSummonerId)
    ally = sortedSummonersByGameRole(ally)

    if ally == None:
        return None

    return [x['summonerId'] for x in ally]


def getTeamColor(session, currentSummonerId):
    '''
    输入 session 以及当前召唤师 id，输出 summonerId -> 颜色的映射
    '''
    data = session['gameData']
    ally, enemy = separateTeams(data, currentSummonerId)

    def makeTeam(team):
        # teamParticipantId => [summonerId]
        tIdToSIds = {}

        for s in team:
            summonerId = s.get('summonerId')
            if not summonerId:
                continue

            teamParticipantId = s.get('teamParticipantId')
            if not teamParticipantId:
                continue

            summoners = tIdToSIds.get(teamParticipantId)

            if not summoners:
                tIdToSIds[teamParticipantId] = [summonerId]
            else:
                tIdToSIds[teamParticipantId].append(summonerId)

        # summonerId => color
        res = {}

        currentColor = 0

        for ids in tIdToSIds.values():
            if len(ids) == 1:
                res[ids[0]] = -1
            else:
                for id in ids:
                    res[id] = currentColor

                currentColor += 1

        return res

    return makeTeam(ally), makeTeam(enemy)


def separateTeams(data, currentSummonerId):
    team1 = data['teamOne']
    team2 = data['teamTwo']
    ally = None
    enemy = None

    for summoner in team1:
        if summoner.get('summonerId') == currentSummonerId:
            ally = team1
            enemy = team2
            break
    else:
        ally = team2
        enemy = team1

    return ally, enemy


async def parseGamesDataConcurrently(games):
    tasks = [parseGameData(game) for game in games]
    return await asyncio.gather(*tasks)


async def parseSummonerGameInfo(item, isRank, currentSummonerId):

    summonerId = item.get('summonerId')

    if summonerId == 0 or summonerId == None:
        return None

    summoner = await connector.getSummonerById(summonerId)

    championId = item.get('championId') or 0
    icon = await connector.getChampionIcon(championId)

    puuid = summoner["puuid"]
    origRankInfo = await connector.getRankedStatsByPuuid(puuid)
    rankInfo = parseRankInfo(origRankInfo)

    try:
        origGamesInfo = await connector.getSummonerGamesByPuuid(
            puuid, 0, 14)

        if cfg.get(cfg.gameInfoFilter) and isRank:
            origGamesInfo["games"] = [
                game for game in origGamesInfo["games"] if game["queueId"] in (420, 440)]

            begIdx = 15
            while len(origGamesInfo["games"]) < 11 and begIdx <= 95:
                endIdx = begIdx + 5
                new = (await connector.getSummonerGamesByPuuid(puuid, begIdx, endIdx))["games"]

                for game in new:
                    if game["queueId"] in (420, 440):
                        origGamesInfo['games'].append(game)

                begIdx = endIdx + 1
    except:
        gamesInfo = []
    else:
        tasks = [parseGameData(game)
                 for game in origGamesInfo["games"][:11]]
        gamesInfo = await asyncio.gather(*tasks)

    _, kill, deaths, assists, _, _ = parseGames(gamesInfo)

    teammatesInfo = [
        getTeammates(
            await connector.getGameDetailByGameId(game["gameId"]),
            puuid
        ) for game in gamesInfo[:1]  # 避免空报错, 查上一局的队友(对手)
    ]

    recentlyChampionName = ""
    fateFlag = None

    if teammatesInfo:  # 判个空, 避免太久没有打游戏的玩家或新号引发异常
        if currentSummonerId in [t['summonerId'] for t in teammatesInfo[0]['summoners']]:
            # 上把队友
            fateFlag = "ally"
        elif currentSummonerId in [t['summonerId'] for t in teammatesInfo[0]['enemies']]:
            # 上把对面
            fateFlag = "enemy"
        recentlyChampionId = max(
            teammatesInfo and teammatesInfo[0]['championId'], 0)  # 取不到时是-1, 如果-1置为0
        recentlyChampionName = connector.manager.champs.get(
            recentlyChampionId)

    return {
        "name": summoner["gameName"] or summoner["displayName"],
        'tagLine': summoner.get("tagLine"),
        "icon": icon,
        'championId': championId,
        "level": summoner["summonerLevel"],
        "rankInfo": rankInfo,
        "gamesInfo": gamesInfo,
        "xpSinceLastLevel": summoner["xpSinceLastLevel"],
        "xpUntilNextLevel": summoner["xpUntilNextLevel"],
        "puuid": puuid,
        "summonerId": summonerId,
        "kda": [kill, deaths, assists],
        "cellId": item.get("cellId"),
        "selectedPosition": item.get("selectedPosition"),
        "fateFlag": fateFlag,
        "isPublic": summoner["privacy"] == "PUBLIC",
        # 最近游戏的英雄 (用于上一局与与同一召唤师游玩之后显示)
        "recentlyChampionName": recentlyChampionName
    }


async def autoPickOrBan(data):
    isAutoBan = cfg.get(cfg.enableAutoBanChampion)
    isAutoSelect = cfg.get(cfg.enableAutoSelectChampion)
    isAutoCompleted = cfg.get(cfg.enableAutoSelectTimeoutCompleted)
    localPlayerCellId = data["data"]["localPlayerCellId"]
    team = data['data']["myTeam"]
    actions = data['data']['actions']
    timer = data['data']['timer']

    if timer["phase"] != "BAN_PICK":
        return

    for actionGroup in actions:
        for action in actionGroup:
            if (action["actorCellId"] == localPlayerCellId
                    and not action["completed"] and action["isInProgress"]):
                actionId = action["id"]
                if isAutoSelect and action["type"] == "pick":
                    isPicked = False
                    for player in team:
                        if player["cellId"] == localPlayerCellId:
                            isPicked = bool(player["championId"]) or bool(
                                player["championPickIntent"])
                            break

                    if not isPicked:
                        championId = connector.manager.getChampionIdByName(
                            cfg.get(cfg.autoSelectChampion))
                        await connector.selectChampion(
                            actionId, championId)

                        # 超时自动锁定
                        if isAutoCompleted:
                            totalTime = timer["totalTimeInPhase"]
                            timeLeft = timer["adjustedTimeLeftInPhase"]
                            if totalTime - timeLeft > 1000:  # 满足情况时, 可能是别人的timer
                                return
                            await asyncio.sleep(int(timeLeft / 1000) - 1)
                            sess = await connector.getChampSelectSession()
                            for player in sess["myTeam"]:
                                if player["cellId"] == localPlayerCellId:  # 找到自己
                                    if player["championPickIntent"] == championId:  # 如果仍然和自动亮起的英雄一样(上厕所去了), 锁一下
                                        await connector.selectChampion(actionId, championId, True)
                                    break

                elif isAutoBan and action["type"] == "ban":
                    championId = connector.manager.getChampionIdByName(
                        cfg.get(cfg.autoBanChampion))

                    # 给队友一点预选的时间
                    await asyncio.sleep(cfg.get(cfg.autoBanDelay))

                    isFriendly = cfg.get(cfg.pretentBan)
                    if isFriendly:
                        for player in team:
                            if championId == player["championPickIntent"]:
                                championId = 0
                                break

                    await connector.banChampion(actionId, championId, True)

                break


async def fixLeagueClientWindow():
    """
    #### 需要管理员权限

    调用 Win API 手动调整窗口大小 / 位置
    详情请见 https://github.com/LeagueTavern/fix-lcu-window

    @return: 当且仅当需要修复且权限不足时返回 `False`
    """

    windowHWnd = win32gui.FindWindow("RCLIENT", "League of Legends")

    # 客户端只有在 DX 9 模式下这个玩意才不是 0
    windowCefHWnd = win32gui.FindWindowEx(
        windowHWnd, 0, "CefBrowserWindow", None)

    if not windowHWnd or not windowCefHWnd:
        return True

    # struct WINDOWPLACEMENT {
    #     UINT  length; (事实上并没有该字段)
    #     UINT  flags;
    #     UINT  showCmd;
    #     POINT ptMinPosition;
    #     POINT ptMaxPosition;
    #     RECT  rcNormalPosition;
    # } ;
    placement = win32gui.GetWindowPlacement(windowHWnd)

    if placement[1] == win32con.SW_SHOWMINIMIZED:
        return True

    # struct RECT {
    #     LONG left;
    #     LONG top;
    #     LONG right;
    #     LONG bottom;
    # }
    windowRect = win32gui.GetWindowRect(windowHWnd)
    windowCefRect = win32gui.GetWindowRect(windowCefHWnd)

    def needResize(rect):
        return (rect[3] - rect[1]) / (rect[2] - rect[0]) != 0.5625

    if not needResize(windowRect) and not needResize(windowCefRect):
        return True

    clientZoom = int(await connector.getClientZoom())

    screenWidth = win32api.GetSystemMetrics(0)
    screenHeight = win32api.GetSystemMetrics(1)

    targetWindowWidth = 1280 * clientZoom
    targetWindowHeight = 720 * clientZoom

    def patchDpiChangedMessage(hWnd):
        dpi = ctypes.windll.user32.GetDpiForWindow(hWnd)
        wParam = win32api.MAKELONG(dpi, dpi)
        lParam = ctypes.pointer((ctypes.c_int * 4)(0, 0, 0, 0))

        WM_DPICHANGED = 0x02E0
        win32api.SendMessage(hWnd, WM_DPICHANGED, wParam, lParam)

    try:
        patchDpiChangedMessage(windowHWnd)
        patchDpiChangedMessage(windowCefHWnd)

        SWP_SHOWWINDOW = 0x0040
        win32gui.SetWindowPos(
            windowHWnd,
            0,
            (screenWidth - targetWindowWidth) // 2,
            (screenHeight - targetWindowHeight) // 2,
            targetWindowWidth, targetWindowHeight,
            SWP_SHOWWINDOW
        )

        win32gui.SetWindowPos(
            windowCefHWnd,
            0,
            0,
            0,
            targetWindowWidth,
            targetWindowHeight,
            SWP_SHOWWINDOW
        )

    except:
        # 需要管理员权限
        return False

    return True
