# -*- coding: utf-8 -*-

# External imports
import collections
import json
import numpy
import os.path
import pandas
import re
import sys

# Internal imports (if any)


SIMPLE_MECHANICS = {u'Charge', u'Stealth', u'Windfury', u'Taunt', u'Divine Shield'}
CARD_COLUMNS = list(map(lambda x: x.lower(), SIMPLE_MECHANICS)) + [u'attack', u'health', u'overload']
_IGNORED_MECHANICS = {u'Combo', u'Battlecry', u'Deathrattle', u'Spellpower', u'Poisonous'}
_TEXT_MECHANICS_PREFIXES = (u'Combo: ', u'Battlecry: ', u'Deathrattle: ')
# _IGNORED_MECHANICS = {u'AffectedBySpellPower', u'Aura', u'AdjacentBuff', u'ImmuneToSpellpower', u'Aura'}
# REMAINING_MECHANICS: Secret, Freeze, HealTarget, Silence, Enrage
_HTML_TAG_PAT = re.compile(r'</?[^>]+>')


def load_json(json_filename):
    """
    Loads a JSON filename with the cards (download it from http://hearthstonejson.com/).

    :param str json_filename: Filename of cards in JSON format.
    :return: a list of cards in dict format.
    """
    if sys.version_info.major == 2:
        with open(json_filename) as fp:
            all_card_sets = json.load(fp, encoding='utf-8')
    else:
        with open(json_filename, encoding='utf-8') as fp:
            all_card_sets = json.load(fp)

    all_cards = sum((v for k, v in all_card_sets.items()
                     if k not in ('Debug', 'Credits', 'Missions', 'System')), list())
    # Select only collectible cards
    all_collectible_cards = (card for card in all_cards
                             if 'collectible' in card and card['collectible'])
    # Remove heroes
    all_collectible_cards = (card for card in all_collectible_cards
                             if 'type' in card and card['type'] != 'Hero')
    # Only interested in these tags for pricer purposes
    interest_tags = ('attack', 'cost', 'durability', 'health', 'mechanics', 'name', 'playerClass', 'text',
                     'type')
    return [{k: v for k, v in card.items() if k in interest_tags}
            for card in all_collectible_cards]


def _parse_text(card):
    mechanics = set(card.get(u'mechanics', list()))
    text = card.get(u'text')
    if text is not None:
        # Remove presentation characters.
        clean_text = _HTML_TAG_PAT.sub('', text).replace('\n', ' ')
        clean_text = re.sub(r'[ ]+', ' ', clean_text)
        # Remove the simple mechanics from the text (they will appear in the card mechanics as well).
        for simple_mechanic in SIMPLE_MECHANICS:
            if simple_mechanic in mechanics:
                clean_text = clean_text.replace(simple_mechanic, '', 1)
        # Remove . from text literals (will be the mechanic separator) to avoid problems.
        clean_text = clean_text.replace('."', '"')
        # Remove leading/trailing characters
        clean_text = re.sub(r'[.,]', '', clean_text).strip()
        if clean_text:
            card[u'text_mechanics'] = clean_text


_mechanics_processors = dict()


def _minion_mechanics_processor(card, discard_unknown_mechanics=True):
    mechanics = set(card.get(u'mechanics', list()))
    if discard_unknown_mechanics and not SIMPLE_MECHANICS.issuperset(mechanics - _IGNORED_MECHANICS):
        return

    # Get attack and health to use them later
    attack = card[u'attack']
    health = card[u'health']

    # Windfury
    if u'Windfury' in mechanics:
        card[u'windfury'] = attack
    # Charge
    if u'Charge' in mechanics:
        card[u'charge'] = attack
    # Stealth
    if u'Stealth' in mechanics:
        card[u'stealth'] = 1
    # Taunt
    if u'Taunt' in mechanics:
        card[u'taunt'] = health
    # Divine Shield
    if u'Divine Shield' in mechanics:
        card[u'divine shield'] = 1

    return card

_mechanics_processors[u'Minion'] = _minion_mechanics_processor


_text_mechanics_processors = list()


def _mechanic_re_processor_factory(re_pattern, attribute_name, attribute_mod=None):
    """
    Generic function factory to generate regular expression based processors.

    :param re_pattern: Regular expression pattern object to match with.
    :param attribute_name: Attribute name to save the value to.
    :param attribute_mod: Group name inside the regular expression to extract.
    :return: a processor for the provided regular expression.
    """
    def _mechanic_re_processor(card, text_mechanics):
        def repl(m):
            groupdict = m.groupdict()
            if u'prefix' in groupdict:
                prefix = groupdict[u'prefix']
                assert not prefix or prefix in _TEXT_MECHANICS_PREFIXES
            attribute_value = int(groupdict.get(u'value', 1))
            attribute_names = (attribute_name, ) if isinstance(attribute_name, str) else attribute_name
            if u'mod' in groupdict:
                key = groupdict[u'mod']
                if key not in attribute_mod:
                    return m.group(0)
                attribute_mods = attribute_mod[key]
                if not isinstance(attribute_mods, collections.Iterable):
                    attribute_mods = (attribute_mods, )
                for attribute_name_, attribute_coeff in zip(attribute_names, attribute_mods):
                    card[attribute_name_] = attribute_coeff * attribute_value
            else:
                for attribute_name_ in attribute_names:
                    card[attribute_name_] = attribute_value
            return ''
        return re_pattern.sub(repl, text_mechanics)
    return _mechanic_re_processor


def _mechanic_text_processor_factory(text_pattern, attribute_name):
    """
    Generic function factory to generate text based processors.

    :param text_pattern: Text pattern to look for.
    :param attribute_name: Attribute name to save the value to.
    :return: a processor for the provided text pattern.
    """
    def _mechanic_text_processor(card, text_mechanics):
        present = text_pattern in text_mechanics
        if present:
            card[attribute_name] = 1
            text_mechanics = text_mechanics.replace(text_pattern, '')
        return text_mechanics
    return _mechanic_text_processor

###
# Overload mechanic.
###
_overload_mechanic_re = re.compile(r'Overload: \((?P<value>\d)\)')
_text_mechanics_processors.append(_mechanic_re_processor_factory(_overload_mechanic_re, u'overload'))

###
# Poisonous mechanic.
###
_poisonous_mechanic_text = u'Destroy any minion damaged by this minion'
_text_mechanics_processors.append(_mechanic_text_processor_factory(_poisonous_mechanic_text, u'poisonous'))

###
# Pacifist mechanic.
###
_pacifist_mechanic_text = u"Can't Attack"
# _text_mechanics_processors.append(_mechanic_text_processor_factory(_pacifist_mechanic_text, u'pacifist'))

###
# Elusive mechanic.
###
_elusive_mechanic_text = u"Can't be targeted by spells or Hero Powers"
_text_mechanics_processors.append(_mechanic_text_processor_factory(_elusive_mechanic_text, u'elusive'))

###
# Clumsy mechanic.
###
_clumsy_mechanic_text = u'50% chance to attack the wrong enemy'
_text_mechanics_processors.append(_mechanic_text_processor_factory(_clumsy_mechanic_text, u'clumsy'))

###
# Deal damage mechanic. First expression.
###
_deal_hero_damage_mechanic_re = re.compile(r'(?P<prefix>\w+: )?Deal (?P<value>\d) damage to (?P<mod>.+)')
_deal_hero_damage_mechanic_mod = {
    'each hero': (1, 1, 0), 'the enemy hero': (0, 1, 0), 'your hero': (1, 0, 0), 'all minions': (0, 0, 1),
    'all minions with Deathrattle': (0, 0, 0.0944), 'ALL characters': (0, 0, 1), 'ALL other characters': (0, 0, 1)}
_text_mechanics_processors.append(_mechanic_re_processor_factory(
    _deal_hero_damage_mechanic_re, (u'deal_own_hero_damage', u'deal_enemy_hero_damage', 'deal_board_damage'),
    attribute_mod=_deal_hero_damage_mechanic_mod))

###
# Deal damage mechanic. Second expression.
###
_deal_damage_mechanic_re = re.compile(r'(?P<prefix>\w+: )?Deal (?P<value>\d) damage( to a random enemy minion)?')
_text_mechanics_processors.append(_mechanic_re_processor_factory(_deal_damage_mechanic_re, u'deal_damage'))

###
# Discard card mechanic.
###
_discard_card_mechanic_re = re.compile(r'(?P<prefix>\w+: )?Discard (?P<mod>\w+) random card(s)?')
_discard_card_mechanic_mod = {'a': 1, 'two': 2}
_text_mechanics_processors.append(_mechanic_re_processor_factory(
    _discard_card_mechanic_re, u'discard_card', attribute_mod=_discard_card_mechanic_mod))

###
# Spell damage mechanic.
###
_spell_damage_mechanic_re = re.compile(r'Spell Damage \+(?P<value>\d)')
_text_mechanics_processors.append(_mechanic_re_processor_factory(_spell_damage_mechanic_re, u'spell_damage'))


def _process_text_mechanics(card, discard_unknown_mechanics=True):
    text_mechanics = card[u'text_mechanics']
    for processor in _text_mechanics_processors:
        text_mechanics = processor(card, text_mechanics).strip()
        if not text_mechanics:
            break
    if text_mechanics and discard_unknown_mechanics:
        # print('Discarding card {} because of remaining text mechanics: {}'.format(card['name'], text_mechanics))
        return
    return card


def process_mechanics(cards, discard_unknown_mechanics=True):
    """
    Process a bunch of cards, extracting the mechanics into attributes. Also, a new attribute *text_mechanics* will
    appear with the *text* of the card, but without the processed mechanics.

    :param list cards: List of cards in dict format to process.
    :param bool discard_unknown_mechanics: Discard unknown *mechanics* and the cards containing them.
    :return: a list of processed cards.
    """
    processed_cards = list()
    for card in cards:
        _parse_text(card)

        type_ = card.get(u'type')
        processor = _mechanics_processors.get(type_)
        if processor is None:
            continue
        card = processor(card, discard_unknown_mechanics=discard_unknown_mechanics)
        if card is None:
            continue

        if u'text_mechanics' in card:
            card = _process_text_mechanics(card, discard_unknown_mechanics=discard_unknown_mechanics)
            if card is None:
                continue

        processed_cards.append(card)
    return processed_cards


def pricing(df, columns=None, coeffs=None, debug=False, price_column=None):
    """
    Price cards present at df, computing the coeffs for the given columns.

    :param :class `pandas.DataFrame`: df: data frame containing the cards to price.
    :param list columns: columns to compute coeffs for (all valid columns if not specified).
    :param coeffs: precomputed set of coeffs for the selected columns.
    :param bool debug: print the computed coeffs
    :param str price_column: name of the column to place the 'price'.
    :return: a matrix with the computed coeffs (if coeffs is provided, return the same coeffs).
    """
    df[u'intrinsic'] = 1
    if columns is None:
        invalid_columns = [
            u'intrinsic', u'name', u'text', u'cost', u'playerClass', u'text_mechanics', u'mechanics', u'type']
        columns = [x for x in df.columns.values if x not in invalid_columns]
    columns = [u'intrinsic'] + columns
    a = df[columns].as_matrix()
    a[numpy.isnan(a)] = 0  # Replace NaN with 0
    if coeffs is None:
        b = 2 * df.as_matrix([u'cost']) + 1
        coeffs = numpy.linalg.lstsq(a, b)[0]
        if debug:
            print(pandas.DataFrame(coeffs.T, columns=columns))
    df[price_column or u'price'] = (numpy.dot(a, coeffs).T[0] - 1) / 2
    return coeffs


if __name__ == '__main__':
    all_sets_filename = os.path.join(os.path.dirname(__file__), '..', 'data', 'AllSets.json')

    # # Uncomment the following lines to update the date file
    # import urllib
    # urllib.urlretrieve ('http://hearthstonejson.com/json/AllSets.json', all_sets_filename)

    my_cards = load_json(all_sets_filename)
    my_processed_cards = process_mechanics(my_cards)
    print('Total cards:', len(my_processed_cards))
    cards_df = pandas.DataFrame(my_processed_cards)
    my_coeffs = pricing(cards_df, debug=True)
    intrinsic = my_coeffs[0][0]
    cards_df[u'diff'] = cards_df[u'price'] - cards_df[u'cost']
    cards_df[u'value'] = cards_df[u'diff'] / (cards_df[u'cost'] - intrinsic)
    print(cards_df[[u'name', u'playerClass', u'cost', u'price', u'diff', u'value']].sort(
        'diff', ascending=False))
    # print(cards_df[cards_df[u'name'] == u'Doomguard'][[u'name', u'playerClass', u'cost', u'price', u'diff', u'value']])
