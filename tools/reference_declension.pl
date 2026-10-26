# Служебный запуск оригинального генератора для контрольных ожиданий.
# perl tools/reference_declension.pl /путь/nlp-rus-zaliz < признаки.json
# На входе массив структур ADB в JSON UTF-8. В рабочей программе не используется.
use strict;
use warnings;
use utf8;
use JSON::PP;
use Encode;
BEGIN { unshift @INC, shift @ARGV or die "Укажите каталог nlp-rus-zaliz\n"; }
use Lingua::RU::Zaliz::Inflect;
my $fresh_optional = (@ARGV && $ARGV[0] eq '--fresh-optional');
my $partners = (@ARGV && $ARGV[0] eq '--partners');

sub convert {
    my ($value, $to_bytes) = @_;
    if (ref($value) eq 'HASH') {
        return { map {
            my $key = $to_bytes ? encode('KOI8-R', $_) : decode('KOI8-R', $_);
            $key => convert($value->{$_}, $to_bytes)
        } keys %$value };
    }
    if (ref($value) eq 'ARRAY') {
        return [map { convert($_, $to_bytes) } @$value];
    }
    return undef if !defined $value;
    return $to_bytes ? encode('KOI8-R', "$value") : decode('KOI8-R', "$value");
}
local $/;
my $entries = JSON::PP->new->utf8->decode(<STDIN>);
my @results;
for my $entry (@$entries) {
    if ($fresh_optional && exists $entry->{'осф'}) {
        # Отдельный режим диагностики: каждая комбинация готовится заново,
        # поэтому кэш причастия другой ветки не скрывает её варианты.
        # Обязательные отклонения сохраняются при включении факультативных.
        my @optional = split //, $entry->{'осф'};
        my %forms;
        for my $mask (0 .. (2 ** scalar(@optional) - 1)) {
            my %branch = %$entry;
            my $mandatory = $entry->{'ос'} || '';
            my $inactive = '';
            for my $i (0 .. $#optional) {
                if ($mask & (1 << $i)) { $mandatory .= $optional[$i]; }
                else { $inactive .= $optional[$i]; }
            }
            $branch{'ос'} = $mandatory;
            if (length($inactive)) { $branch{'осф'} = $inactive; }
            else { delete $branch{'осф'}; }
            my $wi = Lingua::RU::Zaliz::Inflect::get_all_wi(convert(\%branch, 1));
            for my $code (@{$Lingua::RU::Zaliz::Inflect::paradigms{encode('KOI8-R', 'г')}}) {
                push @{$forms{$code}}, @{Lingua::RU::Zaliz::Inflect::inflect($wi, $code)};
            }
        }
        push @results, convert(\%forms, 0);
    } else {
        my $original = convert($entry, 1);
        my ($wi, $forms) = Lingua::RU::Zaliz::Inflect::wi2paradigm([$original]);
        push @results, convert($partners ? $original->{encode('KOI8-R', 'гпрс')} : $forms, 0);
    }
}
print JSON::PP->new->utf8->canonical->encode(\@results);
